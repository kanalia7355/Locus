"""Review-SID-only audit execution, using protected, immutable admitted requests.

The Review service must revalidate remote/source/QA evidence before publication.
This worker cannot read Git/GitHub or sign a review. Owner self-test is fixed
synthetic input only; it is not an endpoint for submitting arbitrary review JSON.
"""

import secrets
import sqlite3
import time
from collections.abc import Callable
from typing import Any

from loop_engine.audit_auth_state import AuthState
from loop_engine.audit_execution import AuditCodexModel
from loop_engine.audit_identity import AuditDeployment
from loop_engine.audit_os_guard import require_private_crash_policy
from loop_engine.audit_packet import PACKET_LIMIT, binding, canonical, decode, digest, hash_value
from loop_engine.audit_profile import auth_command, check_profile, preflight, relay_overrides
from loop_engine.audit_spool import AuditSpool
from loop_engine.audit_supervisor import AuditSupervisor
from loop_engine.audit_transport import AuditRelay
from loop_engine.process import ProcessRunner
from loop_engine.security import SafetyError, fingerprint
from loop_engine.windows_tcp_peer import require_loopback_peer


class AdmittedAuthority:
    def __init__(self, spool: AuditSpool) -> None:
        self.spool = spool

    def current(self, nonce: str) -> dict[str, Any]:
        hash_value(nonce)
        with self.spool._db() as db:
            row = db.execute("SELECT binding FROM packets WHERE nonce=?", (nonce,)).fetchone()
        if row is None:
            raise SafetyError("No protected Review-admitted audit request")
        return binding(decode(row[0], 4096))

    def reserve(self, body: dict[str, Any]) -> None:
        if set(body) != {"operation", "binding", "packet_hash", "size"}:
            raise SafetyError("Closed Review reservation required")
        expected = binding(body["binding"])
        hash_value(body["packet_hash"])
        if type(body["size"]) is not int or not 0 < body["size"] <= PACKET_LIMIT:
            raise SafetyError("Bounded Review reservation required")
        # Fresh wording/QA elapsed times/scope/nonce cannot retry the same source
        # attempt. Actual task/attempt authorization remains Review's authority.
        source = fingerprint(
            {key: value for key, value in expected.items() if key not in {"nonce", "qa", "scope"}}
        )
        with self.spool._db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS admitted_sources "
                "(source TEXT PRIMARY KEY,nonce TEXT UNIQUE NOT NULL)"
            )
            for operation in ("UPDATE", "DELETE"):
                db.execute(
                    f"CREATE TRIGGER IF NOT EXISTS admitted_no_{operation.lower()} "
                    f"BEFORE {operation} ON admitted_sources BEGIN "
                    "SELECT RAISE(ABORT,'immutable audit admission'); END"
                )
            try:
                db.execute("INSERT INTO admitted_sources VALUES (?,?)", (source, expected["nonce"]))
            except sqlite3.IntegrityError:
                raise SafetyError(
                    "Existing source attempt requires reconciliation, not replay"
                ) from None
        # If this local step fails, the source tombstone remains held. Never drop
        # it or retry a new nonce merely to evade uncertain admission.
        self.spool.reserve(expected, body["packet_hash"], body["size"])


class RuntimeBoundary:
    def __init__(self, deployment: AuditDeployment, relay: AuditRelay) -> None:
        self.deployment, self.relay = deployment, relay

    def require(self) -> None:
        require_private_crash_policy(self.deployment)
        check_profile(self.deployment, self.deployment.state / "home")
        self.deployment.require_private_state()
        AuthState(self.deployment.state / "home").require_active()

    def command(self, argv: list[str]) -> list[str]:
        self.require()
        if argv[:2] != [str(self.deployment.runtime / "codex.exe"), "exec"]:
            raise SafetyError("Only fixed read-only audit client invocation permitted")
        return argv + relay_overrides(self.relay.url)


class RuntimeModel:
    def __init__(self, deployment: AuditDeployment) -> None:
        self.deployment = deployment

    def review(
        self, packet: dict[str, Any], *, timeout: float, cancelled: Callable[[], bool]
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        preflight(self.deployment, deadline=deadline, cancelled=cancelled)
        authentication = AuthState(self.deployment.state / "home")
        if authentication.check() != "enrolled":
            raise SafetyError("Enrolled audit identity required")
        authentication.begin("use")
        process = ProcessRunner()
        status = process.run(
            auth_command(self.deployment.runtime / "codex.exe", "login", "status"),
            self.deployment.state,
            timeout=min(15, deadline - time.monotonic()),
            cancelled=cancelled,
            model=True,
            output_limit=8192,
            active_process_limit=1,
        )
        if (
            status.outcome != "exit"
            or status.returncode != 0
            or status.stderr.strip().splitlines()[-1:] != ["Logged in using ChatGPT"]
        ):
            raise SafetyError("Dedicated ChatGPT authentication unavailable; no API fallback")
        authentication.finish("enrolled")
        authentication.begin("use")
        with AuditRelay(
            self.deployment.settings["model"],
            deadline=deadline,
            cancelled=cancelled,
            forwarding=True,
            peer_authorized=lambda connection: require_loopback_peer(
                connection, self.deployment.settings["audit_sid"]
            ),
        ) as relay:
            model = AuditCodexModel(
                self.deployment.runtime / "codex.exe",
                self.deployment.runtime / "contracts",
                self.deployment.state / "empty",
                boundary=RuntimeBoundary(self.deployment, relay),
            )
            result = model.review(packet, timeout=deadline - time.monotonic(), cancelled=cancelled)
            if not relay.accepted:
                raise SafetyError("Audit inference bypassed the mandatory zero-tool relay")
            authentication.finish("enrolled")
            return result


def review_request(
    deployment: AuditDeployment,
    peer: str,
    body: dict[str, Any],
    *,
    deadline: float,
) -> dict[str, Any]:
    if peer != deployment.settings["review_sid"]:
        raise SafetyError("Only the authenticated Review service can admit source packets")
    if not 0 < deadline - time.monotonic() <= 300:
        raise SafetyError("Bounded Review request required")
    spool = AuditSpool(deployment.state)
    authority = AdmittedAuthority(spool)
    if body.get("operation") == "reserve":
        authority.reserve(body)
        return {"status": "recorded", "activated": False}
    supervisor = AuditSupervisor(
        spool,
        authority,
        review_sid=deployment.settings["review_sid"],
        operator_sid=deployment.settings["operator_sid"],
        model=RuntimeModel(deployment),
    )
    return supervisor.dispatch(peer, body, deadline=deadline, cancelled=lambda: False)


def fixed_self_test(deployment: AuditDeployment, *, deadline: float) -> dict[str, Any]:
    """One actual inference per deployed artifact, on an intentionally buggy fixture."""
    intent = deployment.state / "synthetic-model-proof.json"
    if intent.exists():
        saved = decode(intent.read_bytes(), 8192)
        result = saved.get("result")
        if (
            set(saved) != {"identity", "phase", "result", "completed_at"}
            or saved.get("identity") != deployment.identity
            or saved.get("phase") != "complete"
            or not isinstance(result, dict)
            or set(result)
            != {
                "synthetic_only",
                "actual_provider_response_completed",
                "bug_detected",
                "identity",
                "findings_hash",
                "activated",
            }
            or result.get("identity") != deployment.identity
            or result.get("synthetic_only") is not True
            or result.get("actual_provider_response_completed") is not True
            or type(result.get("bug_detected")) is not bool
            or result.get("activated") is not False
        ):
            raise SafetyError("Existing synthetic model trial requires reconciliation")
        hash_value(result["findings_hash"])
        return {**result, "cached": True}
    with intent.open("xb") as stream:
        stream.write(canonical({"identity": deployment.identity, "phase": "started"}))
        stream.flush()
        import os

        os.fsync(stream.fileno())
    metadata = {
        "goal": "Synthetic fixture only: deny guest access to a private resource.",
        "requirements": "authorized('guest', 'private') must return False.",
        "architecture": "A pure synthetic predicate, not a Locus implementation.",
        "acceptance": "Detect the authorization regression and report a blocking finding.",
        "task_spec": "TASK-000: review the intentionally broken synthetic predicate only.",
        "qa": "Synthetic evidence for an inference test only; not real project QA or a CI pass.",
    }
    expected: dict[str, Any] = {key: digest(canonical(value)) for key, value in metadata.items()}
    expected.update(
        policy="a" * 64,
        head="b" * 40,
        base="c" * 40,
        task_id="TASK-000",
        attempt=1,
        scope="security",
        nonce=secrets.token_hex(32),
    )
    packet = {
        "protocol": "locus-audit-packet-v1",
        "binding": expected,
        "metadata": metadata,
        "files": [
            {
                "path": "synthetic_authorization.py",
                "base": "def authorized(actor, resource):\n    return actor == 'owner'\n",
                "head": "def authorized(actor, resource):\n    return True\n",
            }
        ],
    }
    findings = RuntimeModel(deployment).review(
        packet,
        timeout=deadline - time.monotonic(),
        cancelled=lambda: False,
    )
    detected = findings["disposition"] != "pass" and any(
        item["blocking"] or item["severity"] in {"critical", "high"}
        for item in findings["findings"]
    )
    result = {
        "synthetic_only": True,
        "actual_provider_response_completed": True,
        "bug_detected": detected,
        "identity": deployment.identity,
        "findings_hash": fingerprint(findings),
        "activated": False,
    }
    from loop_engine.security import atomic_text

    atomic_text(
        intent,
        canonical(
            {
                "identity": deployment.identity,
                "phase": "complete",
                "result": result,
                "completed_at": time.time(),
            }
        ).decode(),
    )
    return {**result, "cached": False}
