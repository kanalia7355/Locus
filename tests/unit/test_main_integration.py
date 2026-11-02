"""Offline exact-SHA CI and durable post-Push promotion failure/recovery scenarios."""

import copy
import json
import time
from types import SimpleNamespace

import pytest
from test_loop_foundation import task

from loop_engine.main_integration import SOURCE, TARGET, MainIntegration, verified_ci
from loop_engine.policy_migration import PolicyMigration
from loop_engine.reviewer import review_binding
from loop_engine.security import SafetyError, fingerprint
from loop_engine.state_store import StateStore

BEFORE, HEAD = "a" * 40, "b" * 40


def fixture(tmp_path):
    state = StateStore(tmp_path / "state.db")
    work = task()
    state.import_plan("synthetic", "spec", [work])
    state.set_metadata("spec_hash", "spec")
    state.set_metadata("run_budget", {"id": "run", "deadline": time.time() + 180})
    cp = {
        "verified": True,
        "snapshot": {"source": "synthetic"},
        "verification": {"passed": True},
        "workspace": str(tmp_path),
        "committed_head": HEAD,
        "integrated_head": HEAD,
        "pushed_head": HEAD,
        "local_commit_intent": {"tree": "tree"},
    }
    cp["binding"] = review_binding(work, "spec", cp["snapshot"], cp["verification"])
    state.checkpoint(work.id, cp)
    state.evidence(
        "reviews",
        work.id,
        {"task_id": work.id, "disposition": "pass", "findings": []},
        cp["binding"],
    )
    policy = {
        "repository": "fixture/repository",
        "repository_id": "node1",
        "source": SOURCE,
        "target": TARGET,
        "workflows": [
            {"path": ".github/workflows/quality.yml", "digest": "a" * 64, "jobs": ["verify"]},
            {
                "path": ".github/workflows/loop-ci.yml",
                "digest": "b" * 64,
                "jobs": [
                    f"engine ({os}, {v})"
                    for os in ("ubuntu-latest", "windows-latest")
                    for v in ("3.11", "3.13")
                ],
            },
            {
                "path": ".github/workflows/pr-title.yml",
                "digest": "c" * 64,
                "jobs": ["conventional-title"],
            },
        ],
    }
    snapshot = {
        "complete": True,
        "repository_id": "node1",
        "sha": HEAD,
        "branch": SOURCE.removeprefix("refs/heads/"),
        "runs": [
            {
                "path": x["path"],
                "digest": x["digest"],
                "id": i + 1,
                "attempt": 1,
                "latest_attempt": 1,
                "event": "push",
                "app_id": 15368,
                "sha": HEAD,
                "jobs": [
                    {
                        "id": j + 1,
                        "name": name,
                        "status": "completed",
                        "conclusion": "success",
                        "sha": HEAD,
                    }
                    for j, name in enumerate(x["jobs"])
                ],
            }
            for i, x in enumerate(policy["workflows"])
        ],
    }

    class Backend:
        offline = True
        calls = 0
        values = {SOURCE: HEAD, TARGET: BEFORE}

        def refs(self):
            return dict(self.values)

        def checks(self, sha):
            assert sha == HEAD
            return copy.deepcopy(snapshot)

        def update_refs(self, before, after):
            self.calls += 1
            if self.values != {SOURCE: after, TARGET: before}:
                raise SafetyError("atomic comparison rejected")
            self.values[TARGET] = after

    backend = Backend()
    manager = SimpleNamespace(
        root=tmp_path,
        _safe_configuration=lambda: None,
        snapshot=lambda *_: cp["snapshot"],
        _git=lambda args: "tree" if args[0] == "rev-parse" else "",
    )
    integration = MainIntegration(state, manager, policy, backend)
    state.set_metadata(
        "main_range_review",
        {
            "before": BEFORE,
            "sha": HEAD,
            "binding": cp["binding"],
            "policy": fingerprint(policy),
            "passed": True,
        },
    )
    return state, work, cp, policy, snapshot, backend, integration


@pytest.mark.parametrize(
    "change",
    [
        "failed",
        "cancelled",
        "skipped",
        "timed_out",
        "pending",
        "sha",
        "missing",
        "app",
        "attempt",
        "workflow",
        "incomplete",
        "duplicate",
        "malformed",
    ],
)
def test_ci_failures_cannot_promote(tmp_path, change):
    state, work, cp, policy, ci, backend, integration = fixture(tmp_path)
    if change in {"failed", "cancelled", "skipped", "timed_out"}:
        ci["runs"][0]["jobs"][0]["conclusion"] = change
    elif change == "pending":
        ci["runs"][0]["jobs"][0]["status"] = "in_progress"
    elif change == "sha":
        ci["runs"][0]["jobs"][0]["sha"] = BEFORE
    elif change == "missing":
        ci["runs"][0]["jobs"].clear()
    elif change == "app":
        ci["runs"][0]["app_id"] = 999
    elif change == "attempt":
        ci["runs"][0]["latest_attempt"] = 2
    elif change == "workflow":
        ci["runs"][0]["digest"] = "d" * 64
    elif change == "incomplete":
        ci["complete"] = False
    elif change == "malformed":
        ci["runs"][0]["jobs"] = None
    else:
        ci["runs"].append(copy.deepcopy(ci["runs"][0]))
    with pytest.raises(SafetyError):
        integration.deliver(work, cp, cancelled=lambda: False)
    assert backend.calls == 0 and backend.refs()[TARGET] == BEFORE
    assert cp["pushed_head"] == HEAD


@pytest.mark.parametrize("failure", [None, "lost_reply", "remote_confirmed", "recorded"])
def test_recovery_after_update_or_record_failure_never_sends_twice(tmp_path, monkeypatch, failure):
    state, work, cp, _, _, backend, integration = fixture(tmp_path)
    if failure == "lost_reply":
        update = backend.update_refs

        def lost_reply(*args):
            update(*args)
            raise OSError("synthetic reply lost after actual update")

        monkeypatch.setattr(backend, "update_refs", lost_reply)
    elif failure:
        persist = integration._persist

        def failed_write(key, phase, doc):
            if phase == failure:
                raise OSError("synthetic state commit unavailable")
            persist(key, phase, doc)

        monkeypatch.setattr(integration, "_persist", failed_write)
    if failure:
        with pytest.raises(OSError):
            integration.deliver(work, cp, cancelled=lambda: False)
    else:
        assert integration.deliver(work, cp, cancelled=lambda: False)["complete"]
    restarted = MainIntegration(
        StateStore(state.path), integration.git, integration.policy, backend
    )
    assert restarted.deliver(work, cp, cancelled=lambda: False)["main_head"] == HEAD
    assert restarted.deliver(work, cp, cancelled=lambda: False)["complete"]
    assert backend.calls == 1
    with state.connect() as db:
        assert db.execute("SELECT phase FROM main_promotions").fetchone()[0] == "recorded"
        doc = json.loads(db.execute("SELECT document FROM main_promotions").fetchone()[0])
        assert doc["ci"] == fingerprint(doc["ci_evidence"])
        assert doc["ci_evidence"]["runs"][0]["attempt"] == 1
        assert doc["ci_evidence"]["runs"][0]["jobs"][0]["sha"] == HEAD


@pytest.mark.parametrize("reason", ["permission", "protection", "main_race", "source_race"])
def test_atomic_rejection_stays_reserved_and_is_not_replayed(tmp_path, reason, monkeypatch):
    state, work, cp, _, _, backend, integration = fixture(tmp_path)

    def rejected(before, after):
        backend.calls += 1
        if reason == "main_race":
            backend.values[TARGET] = "c" * 40
        if reason == "source_race":
            backend.values[SOURCE] = "c" * 40
        raise SafetyError("synthetic server rejects " + reason)

    monkeypatch.setattr(backend, "update_refs", rejected)
    with pytest.raises(SafetyError):
        integration.deliver(work, cp, cancelled=lambda: False)
    with pytest.raises(SafetyError):
        integration.deliver(work, cp, cancelled=lambda: False)
    assert backend.calls == 1 and cp["pushed_head"] == HEAD
    state.set_metadata("control", "stopped")
    with pytest.raises(SafetyError, match="promotion"):
        PolicyMigration(integration.git.root, state)._idle()


@pytest.mark.parametrize("reason", ["source", "review", "aggregate", "budget", "diverged"])
def test_missing_source_review_budget_or_fast_forward_holds(tmp_path, reason, monkeypatch):
    state, work, cp, _, _, backend, integration = fixture(tmp_path)
    if reason == "source":
        cp["committed_head"] = BEFORE
    elif reason == "review":
        with state.connect() as db:
            db.execute("DELETE FROM reviews")
    elif reason == "aggregate":
        state.set_metadata("main_range_review", None)
    elif reason == "budget":
        state.set_metadata("run_budget", {"id": "run", "deadline": time.time() - 1})
    else:

        def diverged(args):
            if args[0] == "merge-base":
                raise SafetyError("not an ancestor")
            return "tree"

        monkeypatch.setattr(integration.git, "_git", diverged)
    with pytest.raises(SafetyError):
        integration.deliver(work, cp, cancelled=lambda: False)
    assert backend.calls == 0


def test_no_online_backend_or_weakened_required_policy_is_accepted(tmp_path):
    state, _, _, policy, ci, backend, integration = fixture(tmp_path)
    backend.offline = False
    with pytest.raises(SafetyError):
        MainIntegration(state, integration.git, policy, backend)
    backend.offline = True
    policy["workflows"][1]["jobs"].pop()
    with pytest.raises(SafetyError):
        MainIntegration(state, integration.git, policy, backend)
    assert verified_ci(ci, integration.policy, HEAD)
