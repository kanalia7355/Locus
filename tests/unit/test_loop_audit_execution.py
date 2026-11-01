"""Mock-only execution adapter checks; no Codex login or real model invocation."""

import json

import pytest
from test_loop_audit_spool import findings, packet

from loop_engine.audit_execution import AuditCodexModel, contract_artifacts
from loop_engine.audit_packet import decode
from loop_engine.process import ProcessResult
from loop_engine.security import SafetyError


def events(value=None):
    return [
        {"type": "thread.started", "thread_id": "synthetic"},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"type": "reasoning", "text": "discarded"}},
        {
            "type": "item.completed",
            "item": {"type": "agent_message", "text": json.dumps(value or findings())},
        },
        {"type": "turn.completed"},
    ]


class Boundary:
    def __init__(self):
        self.checks = 0

    def require(self):
        self.checks += 1

    def command(self, argv):
        assert "--ephemeral" in argv and "--strict-config" in argv
        return argv


class Process:
    def __init__(self, values=None, outcome="exit", code=0):
        self.values = values if values is not None else events()
        self.outcome = outcome
        self.code = code
        self.calls = []

    def run(self, argv, cwd, **kwargs):
        self.calls.append((argv, cwd, kwargs))
        return ProcessResult(
            self.outcome,
            self.code,
            "\n".join(json.dumps(item) for item in self.values),
            stderr="synthetic diagnostic: must never persist",
        )


def setup(tmp_path, process=None, boundary=True):
    contracts = tmp_path / "contracts"
    contracts.mkdir()
    for name, raw in contract_artifacts().items():
        (contracts / name).write_bytes(raw)
    workspace = tmp_path / "empty"
    workspace.mkdir()
    process = process or Process()
    guard = Boundary() if boundary else None
    runner = AuditCodexModel(
        tmp_path / "pinned-codex.exe", contracts, workspace, boundary=guard, process=process
    )
    _, raw = packet()
    return runner, process, guard, decode(raw)


def test_fixed_readonly_keyring_command_and_no_control_writes(tmp_path):
    runner, process, guard, value = setup(tmp_path)
    before = {path: path.read_bytes() for path in runner.contracts.iterdir()}
    assert runner.review(value, timeout=10, cancelled=lambda: False) == findings()
    assert guard.checks == 3
    argv, cwd, options = process.calls[0]
    assert argv[0] == str(tmp_path / "pinned-codex.exe")
    assert argv[-1] == "-"
    assert argv[argv.index("--sandbox") + 1] == "read-only"
    assert 'cli_auth_credentials_store="keyring"' in argv
    assert all(feature in argv for feature in ("shell_tool", "apps", "plugins", "multi_agent"))
    assert "--skip-git-repo-check" in argv
    assert "--output-last-message" not in argv
    assert cwd == runner.workspace
    assert 0 < options["timeout"] <= 10
    assert options["model"] is True
    assert options["output_limit"] == 1024 * 1024
    assert json.loads(options["stdin"])["packet"] == value
    assert not list(runner.workspace.iterdir())
    assert before == {path: path.read_bytes() for path in runner.contracts.iterdir()}
    assert not (tmp_path / "codex-failure.json").exists()


def test_default_boundary_never_executes_or_reuses_operator_auth(tmp_path):
    runner, process, _, value = setup(tmp_path, boundary=False)
    with pytest.raises(SafetyError, match="not proven"):
        runner.review(value, timeout=10, cancelled=lambda: False)
    assert not process.calls


@pytest.mark.parametrize("name", list(contract_artifacts()))
def test_contract_tampering_stops_before_process(tmp_path, name):
    runner, process, _, value = setup(tmp_path)
    (runner.contracts / name).write_text("{}")
    with pytest.raises(SafetyError, match="contract changed"):
        runner.review(value, timeout=10, cancelled=lambda: False)
    assert not process.calls


@pytest.mark.parametrize(
    "outcome,code",
    [("timeout", 0), ("cancelled", 0), ("exit", 1), ("output_limit", 0), ("spawn_error", None)],
)
def test_unsuccessful_child_never_persists_stdout_or_stderr(tmp_path, outcome, code):
    runner, _, _, value = setup(tmp_path, Process(outcome=outcome, code=code))
    with pytest.raises(SafetyError, match="remains reserved"):
        runner.review(value, timeout=10, cancelled=lambda: False)
    assert sorted(path.name for path in tmp_path.rglob("*") if path.is_file()) == sorted(
        contract_artifacts()
    )


@pytest.mark.parametrize(
    "variant",
    [
        "tool",
        "duplicate",
        "unfinished",
        "failure",
        "extra_field",
        "wrong_task",
        "after_end",
        "no_start",
    ],
)
def test_protocol_or_schema_failure_does_not_become_a_review(tmp_path, variant):
    stream = events()
    if variant == "tool":
        stream.insert(2, {"type": "item.completed", "item": {"type": "command_execution"}})
    elif variant == "duplicate":
        stream.insert(-1, stream[-2])
    elif variant == "unfinished":
        stream.pop()
    elif variant == "failure":
        stream[-1] = {"type": "turn.failed", "error": {"message": "discard"}}
    elif variant == "extra_field":
        stream = events({**findings(), "extra": True})
    elif variant == "wrong_task":
        stream = events({**findings(), "task_id": "TASK-002"})
    elif variant == "after_end":
        stream.append(stream[-1])
    else:
        stream.pop(0)
    runner, _, _, value = setup(tmp_path, Process(stream))
    with pytest.raises(SafetyError, match="raw output withheld"):
        runner.review(value, timeout=10, cancelled=lambda: False)


def test_cancel_before_run_and_changed_workspace(tmp_path):
    runner, process, _, value = setup(tmp_path)
    with pytest.raises(SafetyError):
        runner.review(value, timeout=10, cancelled=lambda: True)
    assert not process.calls
    (runner.workspace / "untrusted.txt").write_text("synthetic")
    with pytest.raises(SafetyError, match="Empty controlled"):
        runner.review(value, timeout=10, cancelled=lambda: False)
    assert not process.calls
