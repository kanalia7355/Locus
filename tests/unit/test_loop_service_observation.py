"""Registration/readiness observations cannot import credentials or authorize signing."""

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

import loop_engine.service_client as client_module
import loop_engine.service_observation as observation
from loop_engine.activation_readiness import assess
from loop_engine.cli import initialize
from loop_engine.planning import source_snapshot
from loop_engine.security import SafetyError, fingerprint
from loop_engine.service_identity import Deployment
from loop_engine.service_inspection import inspect_registration, require_registration


def deployment() -> Deployment:
    return cast(
        Deployment,
        SimpleNamespace(
            identity="a" * 64,
            runtime=Path("synthetic-runtime"),
            settings={
                "operator_sid": "S-1-5-21-1-2-3-1000",
                "roles": {
                    "review": {"account": "locus_loop_review", "sid": "S-1-5-21-1-2-3-1001"},
                    "merge": {"account": "locus_loop_merge", "sid": "S-1-5-21-1-2-3-1002"},
                },
            },
            clients=lambda role: {"S-1-5-21-1-2-3-1000"},
        ),
    )


def facts(value: Deployment) -> dict[str, Any]:
    return {
        "owner": "S-1-5-18",
        "entries": [
            ("S-1-5-18", 0xF01FF, 0),
            ("S-1-5-32-544", 0xF01FF, 0),
            (value.settings["operator_sid"], 0x200B5, 0),
        ],
        "kind": 0x10,
        "start": 3,
        "state": 4,
        "unsafe_access": False,
        "account": ".\\locus_loop_review",
        "binary": f'"{value.runtime / "python.exe"}" -I -B '
        f'"{value.runtime / "service_bootstrap.py"}" --role review '
        f"--manifest-hash {value.identity}",
    }


@pytest.mark.parametrize(
    "defect",
    [
        "owner",
        "duplicate",
        "writer",
        "flags",
        "binary",
        "account",
        "kind",
        "start",
        "state",
        "unsafe_access",
    ],
)
def test_registration_rejects_unsafe_or_different_service(defect: str) -> None:
    value = deployment()
    original = facts(value)
    assert require_registration(value, "review", original)["system_owned"] is True
    changed = deepcopy(original)
    if defect == "duplicate":
        changed["entries"].append(changed["entries"][0])
    elif defect in {"writer", "flags"}:
        changed["entries"][-1] = (
            value.settings["operator_sid"],
            0xF01FF if defect == "writer" else 0x200B5,
            1 if defect == "flags" else 0,
        )
    elif defect == "unsafe_access":
        changed[defect] = True
    else:
        changed[defect] = "different" if isinstance(changed[defect], str) else 0
    with pytest.raises(SafetyError):
        require_registration(value, "review", changed)


def test_cancelled_request_never_opens_scm_or_pipe(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Cancelled call must not perform inspection")

    monkeypatch.setattr("loop_engine.service_inspection.inspect_registration", forbidden)
    monkeypatch.setattr(client_module, "request", forbidden)
    client = client_module.ServiceClient(deployment())
    with pytest.raises(SafetyError, match="cancelled"):
        client.call("review", {"operation": "health"}, cancelled=lambda: True)


def test_registration_failure_never_connects_to_service(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args: Any, **kwargs: Any) -> Any:
        raise SafetyError("SCM ownership differs")

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("No IPC after registration failure")

    monkeypatch.setattr("loop_engine.service_inspection.inspect_registration", blocked)
    monkeypatch.setattr(client_module, "request", forbidden)
    with pytest.raises(SafetyError, match="SCM ownership"):
        client_module.ServiceClient(deployment()).call("review", {"operation": "health"})


def test_registration_time_is_subtracted_from_rpc_window(monkeypatch: pytest.MonkeyPatch) -> None:
    ticks = iter([100.0, 101.0])
    monkeypatch.setattr(client_module.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(
        "loop_engine.service_inspection.inspect_registration", lambda *args, **kwargs: {}
    )

    def request(*args: Any, **kwargs: Any) -> dict[str, Any]:
        assert args[3]["deadline_monotonic"] == 105.0
        assert kwargs["timeout"] == 4.0
        return {"role": "review", "activated": False}

    monkeypatch.setattr(client_module, "request", request)
    result = client_module.ServiceClient(deployment()).call(
        "review", {"operation": "health"}, timeout=5
    )
    assert result["activated"] is False


@pytest.mark.parametrize("outcome", ["timeout", "cancelled"])
def test_inspection_does_not_accept_partial_success_after_owned_job_stop(
    monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    class Process:
        def run(self, argv: list[str], root: Path, **kwargs: Any) -> Any:
            assert argv[1:5] == ["-I", "-B", "-m", "loop_engine.service_inspection"]
            assert kwargs["timeout"] == 2
            return SimpleNamespace(outcome=outcome, returncode=0, stdout='{"running":true}')

    monkeypatch.setattr("loop_engine.process.ProcessRunner", Process)
    with pytest.raises(SafetyError, match="cancelled or timed out"):
        inspect_registration(deployment(), "review", timeout=2)


def test_inspection_accepts_only_complete_bound_boolean_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    valid = {
        "role": "review",
        "identity": "a" * 64,
        "system_owned": True,
        "exact_control_acl": True,
        "operator_cannot_reconfigure": True,
        "running": True,
    }
    response = dict(valid)

    class Process:
        def run(self, argv: list[str], root: Path, **kwargs: Any) -> Any:
            assert kwargs["timeout"] == 15
            return SimpleNamespace(outcome="exit", returncode=0, stdout=json.dumps(response))

    monkeypatch.setattr("loop_engine.process.ProcessRunner", Process)
    assert inspect_registration(deployment(), "review", timeout=120) == valid
    response["running"] = 1
    with pytest.raises(SafetyError, match="Complete registration"):
        inspect_registration(deployment(), "review")


def test_observation_uses_services_and_fixed_owner_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, str]] = []
    registered = {
        "running": True,
        "system_owned": True,
        "exact_control_acl": True,
        "operator_cannot_reconfigure": True,
    }

    class Client:
        deployment = deployment()

        def call(self, role: str, document: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
            operation = document["operation"]
            calls.append((role, operation))
            assert 0 < kwargs["timeout"] <= 120
            if operation == "health":
                return {
                    "role": role,
                    "identity": self.deployment.identity,
                    "activated": False,
                    **{
                        key: True
                        for key in (
                            "isolated_account",
                            "key_present",
                            "cross_role_key_absent",
                            "other_state_denied",
                            "source_write_denied",
                        )
                    },
                }
            assert operation == "verify"
            return {"role": role, "authenticated": True, "activated": False}

    class Policy:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def observe(self) -> dict[str, Any]:
            return {"issues": []}

    class Process:
        def run(self, argv: list[str], root: Path, **kwargs: Any) -> Any:
            assert argv == [
                "gh",
                "pr",
                "view",
                "6",
                "--repo",
                "kanalia7355/Locus",
                "--json",
                "number,baseRefName,autoMergeRequest",
            ]
            return SimpleNamespace(
                outcome="exit",
                returncode=0,
                stdout=json.dumps({"number": 6, "baseRefName": "main", "autoMergeRequest": None}),
            )

    def forbidden() -> Any:
        raise AssertionError("Observation must not read owner App keys")

    monkeypatch.setattr(client_module, "WindowsAppVault", forbidden)
    monkeypatch.setattr(observation, "ServiceClient", Client)
    monkeypatch.setattr(observation, "ServicePolicyObserver", Policy)
    monkeypatch.setattr(
        observation,
        "inspect_registration",
        lambda deployed, role, **kwargs: {
            **registered,
            "role": role,
            "identity": deployed.identity,
        },
    )
    monkeypatch.setattr(observation, "ProcessRunner", Process)
    remote = observation.observe(tmp_path, 6)
    assert calls == [
        ("review", "health"),
        ("review", "verify"),
        ("merge", "health"),
        ("merge", "verify"),
    ]
    initialize(tmp_path, "Synthetic service readiness Goal")
    report = assess(tmp_path, fingerprint(source_snapshot(tmp_path)), remote=remote)
    gates = {item["id"]: item["status"] for item in report["gates"]}
    assert gates["preparation_services"] == "passed"
    assert gates["isolated_signer"] == gates["controller_broker_connection"] == "blocked"
    assert report["ready_for_activation_approval"] is False
    assert report["merge_authorized"] is False
    remote["preparation"]["review"]["health"]["source_write_denied"] = False
    changed = assess(tmp_path, fingerprint(source_snapshot(tmp_path)), remote=remote)
    assert (
        next(gate for gate in changed["gates"] if gate["id"] == "preparation_services")["status"]
        == "blocked"
    )
