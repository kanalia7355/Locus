"""Read-only readiness inventory; unmet engineering cannot be approved away."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from loop_engine.config import load
from loop_engine.planning import source_snapshot
from loop_engine.runtime_diagnostics import require_receipt
from loop_engine.security import fingerprint, within


def frozen_hash(root: Path) -> str | None:
    path = within(root, ".loop/runtime/state.sqlite3")
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        row = db.execute("SELECT value FROM metadata WHERE key='spec_hash'").fetchone()
        value = json.loads(row[0]) if row else None
        return value if isinstance(value, str) else None


def applied_migration(root: Path, specification_hash: str | None) -> bool:
    path = within(root, ".loop/runtime/state.sqlite3")
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        if not db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='policy_migrations'"
        ).fetchone():
            return False
        row = db.execute(
            "SELECT document FROM policy_migrations WHERE phase='applied' "
            "ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        return bool(row and fingerprint(json.loads(row[0])["new"]) == specification_hash)


def assess(
    root: Path, frozen_specification_hash: str | None, *, remote: dict[str, Any] | None = None
) -> dict[str, Any]:
    config = load(root / ".loop/config.yaml")
    snapshot = source_snapshot(root)
    remote = remote or {}
    gates: list[dict[str, Any]] = []

    def add(identity: str, passed: bool, evidence: str, action: str) -> None:
        gates.append(
            {
                "id": identity,
                "status": "passed" if passed else "blocked",
                "evidence": evidence,
                "remaining_action": "" if passed else action,
            }
        )

    add(
        "frozen_specification",
        fingerprint(snapshot) == frozen_specification_hash,
        "Current source/policy compared with the persisted frozen specification.",
        "Reconcile source/policy changes using a versioned migration; preserve old records.",
    )
    try:
        require_receipt(root)
        receipt = True
    except (ValueError, OSError):
        receipt = False
    add(
        "runtime_identity",
        receipt,
        "Containment receipt checked against current runtime identity.",
        "Run doctor --check-sandbox after the final independently reviewed source is frozen.",
    )
    add(
        "review_app_auth",
        remote.get("review_authenticated") is True,
        "Fresh read-only Review App probe." if remote else "No live App probe requested.",
        "Authenticate the repo-only Review installation using its saved local key.",
    )
    add(
        "merge_app_policy",
        remote.get("merge_authenticated") is True,
        "Fresh Merge App policy probe." if remote else "No live App probe requested.",
        "Authenticate the repo-only Merge installation and read protection.",
    )
    preparation = remote.get("preparation", {})

    def prepared_role(role: str) -> bool:
        registration = preparation.get(role, {}).get("registration", {})
        health = preparation.get(role, {}).get("health", {})
        return (
            remote.get(role + "_authenticated") is True
            and registration.get("role") == health.get("role") == role
            and bool(registration.get("identity"))
            and registration.get("identity") == health.get("identity")
            and all(
                registration.get(key) is True
                for key in (
                    "running",
                    "system_owned",
                    "exact_control_acl",
                    "operator_cannot_reconfigure",
                )
            )
            and all(
                health.get(key) is True
                for key in (
                    "key_present",
                    "isolated_account",
                    "cross_role_key_absent",
                    "other_state_denied",
                    "source_write_denied",
                )
            )
            and health.get("activated") is False
        )

    prepared = bool(preparation) and all(prepared_role(role) for role in ("review", "merge"))
    add(
        "preparation_services",
        prepared,
        "Fresh registration, denied mutation capability, health and App service probes.",
        "Deploy and verify both isolated prepare services; observation never imports a key.",
    )
    observation = remote.get("policy", {})
    add(
        "remote_protection",
        bool(observation) and observation.get("issues") == [],
        "Fresh App policy observer compared classic protection and both writer rulesets.",
        "Apply and read back App-bound independent review plus both exclusive-writer rulesets.",
    )
    graph = remote.get("pull_state", {})
    add(
        "native_auto_merge_absent",
        bool(graph) and "autoMergeRequest" in graph and graph["autoMergeRequest"] is None,
        "Fresh fixed-query pull-request state." if graph else "No live PR probe requested.",
        "Remove native future-head auto-merge before any App approval is published.",
    )
    add(
        "main_target",
        config["github"]["base"] == "main",
        "Frozen GitHub base inspected.",
        "Prepare and approve the versioned integration-base migration.",
    )
    add(
        "development_scope",
        config["development"]["enabled"] is True and bool(config["development"]["allowed_paths"]),
        "Frozen Development configuration inspected.",
        "Approve Goal/path scope and migrate Development policy without resetting tasks.",
    )
    add(
        "versioned_migration",
        applied_migration(root, frozen_specification_hash),
        "Approved migration apply/recovery code exists; applied state checked read-only.",
        "Approve and apply the exact migration after deployment; retain all prior evidence.",
    )
    # Deliberate engineering blockers: no receipt JSON or human pass flag is
    # allowed to pretend these unavailable production components are deployed.
    for identity, evidence, action in (
        (
            "isolated_signer",
            "Prepare-only services are verified; production signing authority is not connected."
            if prepared
            else "No verified isolated preparation deployment is connected.",
            "Connect audited production authority and resolve legacy key custody.",
        ),
        (
            "controller_broker_connection",
            "Publisher/transport cores exist; live Controller wiring is absent.",
            "Connect bounded services, protected Controller evidence and Broker recovery.",
        ),
        (
            "live_writer_proofs",
            "No live race/crash/writer-denial proof has been established.",
            "Prove writer denial, late writes, crashes, revocation and recovery in approved scope.",
        ),
        (
            "live_full_cycle",
            "No complete live App/Broker/Development cycle is established.",
            "Prove implementation, CI repair, review, App publication, merge and next task live.",
        ),
        (
            "final_audit",
            "No final deployed-system independent audit/activation record exists.",
            "Audit the final deployment independently; bind activation to its reviewed identity.",
        ),
    ):
        add(identity, False, evidence, action)
    return {
        "ready_for_activation_approval": all(gate["status"] == "passed" for gate in gates),
        "merge_authorized": False,
        "controller_started": False,
        "specification_hash": fingerprint(snapshot),
        "gates": gates,
        "note": "Approval cannot substitute for missing implementation, deployment or live proof.",
    }
