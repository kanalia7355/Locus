"""Owner-relative trial approval: synthetic state, no auth, CLI or provider."""

import copy
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from test_trial_input_binding_v3 import fixture as input_fixture

from loop_engine import trial_authorization as activation
from loop_engine.approval import ApprovalQueue
from loop_engine.c_min_trial import PLAN_HASH, SCHEMA, authorize, reserve, status
from loop_engine.cli import initialize
from loop_engine.security import SafetyError, fingerprint


def fixture(tmp_path, monkeypatch):
    state = initialize(tmp_path, "Synthetic activation")
    spec, *_ = input_fixture()
    workspace = tmp_path / ".loop/runtime/probes/c-min-single-validation"
    workspace.mkdir(parents=True)
    (workspace / "synthetic.txt").write_bytes(b"C_MIN_SYNTHETIC_ONLY\n")
    profile = {"synthetic": True}
    permit = {
        "purpose": "c-min-single-validation",
        "runtime": "runtime",
        "artifact": "artifact",
        "workspace": str(workspace),
        "plan": PLAN_HASH,
        "input_hash": "pending",
        "profile": fingerprint(profile),
        "history": "a" * 64,
        "max_calls": 1,
        "refresh": "official-existing-secure-backend-only",
        "offline_review": "b" * 64,
        "input_version": spec["version"],
    }
    spec["launch"] = {
        **{k: permit[k] for k in ("runtime", "artifact", "workspace", "profile", "history")},
        "model": "gpt-6.1-sol",
        "destination": "https://chatgpt.com/backend-api/codex/responses",
        "argv": ["synthetic-cli"],
        "schema": fingerprint(SCHEMA),
    }
    permit["input_hash"] = fingerprint(spec)
    request = {
        "version": activation.VERSION,
        "execution_seconds": 180,
        "permit": permit,
        "registrations": {
            "c_min_auth_profile": profile,
            "c_min_trial_input_contract": spec,
            "c_min_trial_history": {
                "binding": permit["history"],
                "reconciled": True,
                "additional_slots": 1,
            },
            "c_min_trial_offline_review": {
                "binding": permit["offline_review"],
                "runtime": "runtime",
                "passed": True,
            },
        },
    }
    # Keep static contract validation; replace only operator environment inspection.
    monkeypatch.setattr(
        activation, "validate_context", lambda root, value: activation.validate_request(value)
    )
    monkeypatch.setattr("loop_engine.runtime_diagnostics.runtime_identity", lambda root: "runtime")
    return state, workspace, request


def choose(state, decision, request, action="approve"):
    ApprovalQueue(state).resolve(
        [
            {
                "id": decision,
                "action": action,
                "target_hash": fingerprint(request),
                "reason": "Synthetic state only, not a live permission",
            }
        ],
        "fixture",
    )


def test_waiting_days_starts_no_clock_then_owner_decision_fixes_exact_deadline(
    tmp_path, monkeypatch
):
    state, work, request = fixture(tmp_path, monkeypatch)
    clock = [1000.0]
    monkeypatch.setattr(time, "time", lambda: clock[0])
    decision = activation.prepare(tmp_path, state, request)
    clock[0] += 7 * 86400
    assert activation.prepare(tmp_path, state, request) == decision
    assert state.metadata("c_min_trial_permit") is None
    assert state.metadata("c_min_auth_profile") is None
    assert status(state)["phase"] == "absent"
    choose(state, decision, request)
    permit = state.metadata("c_min_trial_permit")
    assert permit == {
        **request["permit"],
        "expires": clock[0] + 180,
        "approval_scope": fingerprint(request),
    }
    assert activation.authorized(state, permit, decision)
    assert authorize(tmp_path, state, work, "artifact", decision) == permit
    recovered = type(state)(state.path)
    assert recovered.metadata("c_min_trial_permit") == permit
    clock[0] += 181
    assert not activation.authorized(recovered, permit, decision)
    with pytest.raises(SafetyError):
        authorize(tmp_path, recovered, work, "artifact", decision)
    with pytest.raises((ValueError, SafetyError)):
        choose(recovered, decision, request)
    with pytest.raises(SafetyError):
        activation.prepare(tmp_path, recovered, request)
    assert recovered.metadata("c_min_trial_permit") == permit


@pytest.mark.parametrize("action", ["reject", "revise"])
def test_nonapproval_grants_nothing(tmp_path, monkeypatch, action):
    state, _, request = fixture(tmp_path, monkeypatch)
    decision = activation.prepare(tmp_path, state, request)
    choose(state, decision, request, action)
    assert state.metadata("c_min_trial_permit") is None
    assert state.metadata("c_min_auth_profile") is None
    assert status(state)["phase"] == "absent"


def test_activation_and_owner_decision_rollback_together(tmp_path, monkeypatch):
    state, _, request = fixture(tmp_path, monkeypatch)
    decision = activation.prepare(tmp_path, state, request)
    original = state._event

    def failed(db, kind, *args):
        if kind == "approval.resolved":
            raise RuntimeError("synthetic commit interruption")
        return original(db, kind, *args)

    monkeypatch.setattr(state, "_event", failed)
    with pytest.raises(RuntimeError):
        choose(state, decision, request)
    assert ApprovalQueue(state).status(None, "scope", fingerprint(request)) == "pending"
    assert state.metadata("c_min_trial_permit") is None
    assert state.metadata("c_min_auth_profile") is None
    with state.connect() as db:
        exists = db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='c_min_trial_activations'"
        ).fetchone()
        assert not exists or not db.execute("SELECT 1 FROM c_min_trial_activations").fetchone()
    monkeypatch.setattr(state, "_event", original)
    choose(state, decision, request)
    assert activation.authorized(state, state.metadata("c_min_trial_permit"), decision)


def test_stale_context_and_existing_legacy_permit_cannot_be_adopted(tmp_path, monkeypatch):
    state, _, request = fixture(tmp_path, monkeypatch)
    decision = activation.prepare(tmp_path, state, request)
    monkeypatch.setattr(
        activation, "validate_context", lambda *_: (_ for _ in ()).throw(SafetyError("stale"))
    )
    with pytest.raises(SafetyError):
        choose(state, decision, request)
    assert state.metadata("c_min_trial_permit") is None
    assert ApprovalQueue(state).status(None, "scope", fingerprint(request)) == "pending"
    monkeypatch.setattr(
        activation, "validate_context", lambda root, value: activation.validate_request(value)
    )
    old = {"expires": 1, "legacy": "expired, not reusable"}
    state.set_metadata("c_min_trial_permit", old)
    with pytest.raises(SafetyError):
        choose(state, decision, request)
    assert state.metadata("c_min_trial_permit") == old


@pytest.mark.parametrize(
    "change", ["expiry", "scope", "decision", "review", "request", "revoked", "clock_backwards"]
)
def test_activation_tampering_revocation_and_clock_reversal_fail_closed(
    tmp_path, monkeypatch, change
):
    state, work, request = fixture(tmp_path, monkeypatch)
    decision = activation.prepare(tmp_path, state, request)
    choose(state, decision, request)
    permit = state.metadata("c_min_trial_permit")
    if change == "expiry":
        permit["expires"] += 1
        state.set_metadata("c_min_trial_permit", permit)
    elif change == "scope":
        permit["approval_scope"] = "wrong"
        state.set_metadata("c_min_trial_permit", permit)
    elif change == "review":
        state.set_metadata("c_min_trial_offline_review", {})
    elif change == "request":
        altered = copy.deepcopy(request)
        altered["permit"]["max_calls"] = 2
        state.set_metadata("c_min_trial_request", altered)
    elif change == "clock_backwards":
        with state.connect() as db:
            at = db.execute("SELECT decided FROM decisions WHERE id=?", (decision,)).fetchone()[0]
        monkeypatch.setattr(time, "time", lambda: at - 1)
    else:
        with state.transaction() as db:
            if change == "revoked":
                db.execute("UPDATE decisions SET status='rejected' WHERE id=?", (decision,))
            else:
                db.execute("UPDATE c_min_trial_activations SET document='{}'")
    assert not activation.authorized(state, permit, decision)
    with pytest.raises(SafetyError):
        authorize(tmp_path, state, work, "artifact", decision)


def test_concurrent_approval_consumes_one_activation_and_unknown_slot_never_replays(
    tmp_path, monkeypatch
):
    state, _, request = fixture(tmp_path, monkeypatch)
    decision = activation.prepare(tmp_path, state, request)

    def approve():
        try:
            choose(state, decision, request)
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: approve(), range(2))) == [False, True]
    permit = state.metadata("c_min_trial_permit")
    reserve(state, permit, "artifact")
    with pytest.raises(SafetyError):
        reserve(state, permit, "artifact")
    with pytest.raises(SafetyError):
        activation.prepare(tmp_path, state, request)
    with state.connect() as db:
        assert db.execute("SELECT count(*) FROM c_min_trial_activations").fetchone()[0] == 1


@pytest.mark.parametrize(
    "field", ["execution_seconds", "input", "profile", "history", "destination", "expiry"]
)
def test_unapproved_scope_expansion_is_rejected_before_request(tmp_path, monkeypatch, field):
    state, _, request = fixture(tmp_path, monkeypatch)
    if field == "execution_seconds":
        request[field] = 181
    elif field == "input":
        request["registrations"]["c_min_trial_input_contract"]["body"]["model"] = "other"
    elif field == "profile":
        request["registrations"]["c_min_auth_profile"] = {"other": True}
    elif field == "history":
        request["registrations"]["c_min_trial_history"]["additional_slots"] = 2
    elif field == "destination":
        request["registrations"]["c_min_trial_input_contract"]["launch"]["destination"] = (
            "https://example.invalid"
        )
    else:
        request["permit"]["expires"] = 1
    with pytest.raises(SafetyError):
        activation.prepare(tmp_path, state, request)
    assert not ApprovalQueue(state).decisions()


@pytest.mark.parametrize(
    "mode", ["success", "revoked_before_resume", "revoked_after_send", "revoked_poll"]
)
def test_actual_shared_adapter_honors_owner_activation_at_every_stage(tmp_path, monkeypatch, mode):
    from test_c_min_trial import test_shared_adapter_one_shot_complete_input_and_no_replay as case

    case(tmp_path, monkeypatch, mode, "v3", owner_activated=True)


def test_expired_activation_cannot_issue_final_trial_proof(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from loop_engine.c_min_trial import record_result

    state, _, request = fixture(tmp_path, monkeypatch)
    decision = activation.prepare(tmp_path, state, request)
    choose(state, decision, request)
    permit = state.metadata("c_min_trial_permit")
    monkeypatch.setattr(time, "time", lambda: permit["expires"] + 1)
    with pytest.raises(SafetyError, match="owner activation"):
        record_result(state, SimpleNamespace(), "never-advanced", permit, "")
