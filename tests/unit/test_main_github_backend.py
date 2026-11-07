"""gh protocol responses only; fake process, no GitHub calls/auth or main mutations."""

import base64
import hashlib
import json
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from test_main_integration import BEFORE, HEAD
from test_main_integration import fixture as promotion_fixture

from loop_engine.main_github_backend import OfflineGitHubBackend
from loop_engine.main_integration import SOURCE, TARGET, MainIntegration, verified_ci
from loop_engine.process import ProcessResult, ProcessRunner
from loop_engine.security import SafetyError, fingerprint


def fixture(tmp_path):
    state, work, cp, policy, _, _, promotion = promotion_fixture(tmp_path)
    runs = []
    jobs = {}
    check_runs = {}
    contents = {}
    for i, workflow in enumerate(policy["workflows"]):
        data = ("public synthetic " + workflow["path"]).encode()
        workflow["digest"] = hashlib.sha256(data).hexdigest()
        contents[workflow["path"]] = {
            "path": workflow["path"],
            "type": "file",
            "encoding": "base64",
            "size": len(data),
            "content": base64.b64encode(data).decode(),
        }
        run_id = 10 + i
        runs.append(
            {
                "id": run_id,
                "path": workflow["path"],
                "head_sha": HEAD,
                "head_branch": "loop/local-development",
                "event": "push",
                "run_attempt": 2,
                "status": "completed",
                "conclusion": "success",
                "check_suite_id": i + 20,
                "repository": {"node_id": "node1"},
                "head_repository": {"node_id": "node1"},
            }
        )
        jobs[run_id] = []
        for j, name in enumerate(workflow["jobs"]):
            identity = 100 + i * 10 + j
            jobs[run_id].append(
                {
                    "id": identity,
                    "run_id": run_id,
                    "run_attempt": 2,
                    "head_sha": HEAD,
                    "name": name,
                    "status": "completed",
                    "conclusion": "success",
                    "check_run_url": f"https://api.github.com/repos/fixture/repository/check-runs/{identity}",
                }
            )
            check_runs[identity] = {
                "id": identity,
                "app": {"id": 15368},
                "head_sha": HEAD,
                "name": name,
                "status": "completed",
                "conclusion": "success",
                "check_suite": {"id": i + 20},
            }

    class Process:
        offline = True

        def __init__(self):
            self.calls = []
            self.refs = {SOURCE: HEAD, TARGET: BEFORE}
            self.errors = False
            self.reviews = None
            self.rules = []
            self.owner = "fixture"
            self.push = True
            self.lost_reply = False

        def run(self, args, cwd, **options):
            self.calls.append((args, options))
            assert args[:4] == ["gh", "api", "--hostname", "github.com"]
            assert 0 < options["timeout"] <= 30
            if "POST" in args:
                assert args[-3:] == ["graphql", "--input", "-"]
                payload = json.loads(options["stdin"])
                assert "updateRefs" in payload["query"]
                assert (
                    "force" not in payload["query"]
                )  # Values are structured variables, not text injection.
                updates = payload["variables"]["input"]["refUpdates"]
                assert len(updates) == 2 and all(u["force"] is False for u in updates)
                if self.errors:
                    return ProcessResult("exit", 0, json.dumps({"errors": [{"type": "FORBIDDEN"}]}))
                if any(self.refs[u["name"]] != u["beforeOid"] for u in updates):
                    return ProcessResult("exit", 0, json.dumps({"errors": [{"type": "RACE"}]}))
                for update in updates:
                    self.refs[update["name"]] = update["afterOid"]
                if self.lost_reply:
                    return ProcessResult("timeout", None)
                return ProcessResult("exit", 0, '{"data":{"updateRefs":{"clientMutationId":null}}}')
            endpoint = args[-1]
            query = parse_qs(urlsplit(endpoint).query)
            path = endpoint.split("?", 1)[0]
            suffix = path.removeprefix("repos/fixture/repository")
            if endpoint == "user":
                data = {"login": self.owner}
            elif endpoint == "repos/fixture/repository":
                data = {
                    "node_id": "node1",
                    "full_name": "fixture/repository",
                    "permissions": {"push": self.push},
                }
            elif suffix.startswith("/git/ref/"):
                ref = "refs/" + suffix.removeprefix("/git/ref/")
                data = {"ref": ref, "object": {"sha": self.refs[ref], "type": "commit"}}
            elif suffix == "/actions/runs":
                assert query["head_sha"] == [HEAD] and query["event"] == ["push"]
                page = int(query["page"][0])
                data = {
                    "total_count": len(runs),
                    "workflow_runs": runs[(page - 1) * 100 : page * 100],
                }
            elif suffix.startswith("/contents/"):
                assert query["ref"] == [HEAD]
                data = contents[suffix.removeprefix("/contents/")]
            elif "/attempts/" in suffix:
                run_id = int(suffix.split("/")[3])
                assert suffix.endswith("/attempts/2/jobs")
                page = int(query["page"][0])
                data = {
                    "total_count": len(jobs[run_id]),
                    "jobs": jobs[run_id][(page - 1) * 100 : page * 100],
                }
            elif suffix.startswith("/actions/runs/"):
                data = next(x for x in runs if x["id"] == int(suffix.rsplit("/", 1)[1]))
            elif suffix.startswith("/check-runs/"):
                data = check_runs[int(suffix.rsplit("/", 1)[1])]
            elif suffix == "/branches/main":
                data = {"protected": True, "commit": {"sha": self.refs[TARGET]}}
            elif suffix == "/branches/main/protection":
                data = {
                    "required_pull_request_reviews": self.reviews,
                    "enforce_admins": {"enabled": True},
                    "required_status_checks": {
                        "strict": True,
                        "checks": [
                            {"context": name, "app_id": 15368}
                            for w in policy["workflows"]
                            for name in w["jobs"]
                        ],
                    },
                    "allow_force_pushes": {"enabled": False},
                    "allow_deletions": {"enabled": False},
                }
            elif suffix == "/rules/branches/main":
                data = self.rules
            else:
                raise AssertionError("Unexpected offline endpoint")
            return ProcessResult("exit", 0, json.dumps(data))

    process = Process()
    state.set_metadata("control", "running")
    manager = SimpleNamespace(
        process=process, state=state, root=tmp_path, config={"repository": "fixture/repository"}
    )
    backend = OfflineGitHubBackend(manager, policy, time.time() + 120)
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
    return (
        state,
        work,
        cp,
        policy,
        runs,
        jobs,
        check_runs,
        contents,
        process,
        backend,
        promotion.git,
    )


def test_full_protocol_delivers_and_records_exact_checks_without_retry(tmp_path):
    state, work, cp, policy, _, _, _, _, process, backend, git = fixture(tmp_path)
    observed = backend.checks(HEAD)
    assert verified_ci(observed, policy, HEAD)
    gate = MainIntegration(state, git, policy, backend)
    assert gate.deliver(work, cp, cancelled=lambda: False)["main_head"] == HEAD
    assert gate.deliver(work, cp, cancelled=lambda: False)["complete"]
    assert sum("POST" in args for args, _ in process.calls) == 1
    with state.connect() as db:
        doc = json.loads(db.execute("SELECT document FROM main_promotions").fetchone()[0])
        assert doc["ci_evidence"]["runs"][0]["attempt"] == 2


@pytest.mark.parametrize(
    "change",
    [
        "job_sha",
        "publisher",
        "suite",
        "workflow_bytes",
        "workflow_sha",
        "repo",
        "attempt",
        "pending",
        "cancelled",
        "run_pending",
        "run_failed",
        "missing_suite",
    ],
)
def test_ci_protocol_mismatches_never_send_update(tmp_path, change):
    state, work, cp, policy, runs, jobs, checks, contents, process, backend, git = fixture(tmp_path)
    if change == "job_sha":
        jobs[10][0]["head_sha"] = BEFORE
    elif change == "publisher":
        checks[100]["app"]["id"] = 999
    elif change == "suite":
        checks[100]["check_suite"]["id"] = 999
    elif change == "workflow_bytes":
        contents[policy["workflows"][0]["path"]]["content"] = "invalid"
    elif change == "workflow_sha":
        runs[0]["head_sha"] = BEFORE
    elif change == "repo":
        runs[0]["repository"]["node_id"] = "another"
    elif change == "attempt":
        jobs[10][0]["run_attempt"] = 1
    elif change == "pending":
        jobs[10][0]["status"] = checks[100]["status"] = "in_progress"
    elif change == "run_pending":
        runs[0]["status"] = "in_progress"
    elif change == "run_failed":
        runs[0]["conclusion"] = "failure"
    elif change == "missing_suite":
        runs[0].pop("check_suite_id")
    else:
        jobs[10][0]["conclusion"] = checks[100]["conclusion"] = "cancelled"
    with pytest.raises(SafetyError):
        MainIntegration(state, git, policy, backend).deliver(work, cp, cancelled=lambda: False)
    assert not any("POST" in args for args, _ in process.calls)


@pytest.mark.parametrize(
    "change", ["permission", "user", "pr_protection", "unknown_rule", "graphql"]
)
def test_permission_policy_and_graphql_errors_hold_without_fallback(tmp_path, change):
    state, work, cp, policy, _, _, _, _, process, backend, git = fixture(tmp_path)
    if change == "permission":
        process.push = False
    elif change == "user":
        process.owner = "another"
    elif change == "pr_protection":
        process.reviews = {"required_approving_review_count": 1}
    elif change == "unknown_rule":
        process.rules = [{"type": "unknown"}]
    else:
        process.errors = True
    gate = MainIntegration(state, git, policy, backend)
    with pytest.raises(SafetyError):
        gate.deliver(work, cp, cancelled=lambda: False)
    count = sum("POST" in args for args, _ in process.calls)
    assert count == (1 if change == "graphql" else 0)
    with pytest.raises(SafetyError):
        gate.deliver(work, cp, cancelled=lambda: False)
    assert sum("POST" in args for args, _ in process.calls) == count


def test_real_process_rejected_before_any_github_or_auth_call(tmp_path):
    *_, backend, _ = fixture(tmp_path)
    manager = SimpleNamespace(
        process=ProcessRunner(), root=tmp_path, config={"repository": "fixture/repository"}
    )
    with pytest.raises(SafetyError, match="not activated"):
        OfflineGitHubBackend(manager, backend.policy, time.time() + 30)


def test_pagination_consumes_all_pages_and_rejects_truncated_or_changing_totals(
    tmp_path, monkeypatch
):
    *_, backend, _ = fixture(tmp_path)
    pages = []

    def api(endpoint):
        pages.append(endpoint)
        page = int(parse_qs(urlsplit(endpoint).query)["page"][0])
        return {
            "total_count": 101,
            "items": [{"id": i} for i in range((page - 1) * 100, min(page * 100, 101))],
        }

    monkeypatch.setattr(backend, "_api", api)
    assert len(backend._pages("synthetic", "items")) == 101
    assert len(pages) == 2
    monkeypatch.setattr(backend, "_api", lambda _: {"total_count": 101, "items": [{"id": 1}]})
    with pytest.raises(SafetyError):
        backend._pages("synthetic", "items")


def test_lost_graphql_reply_reconciles_readonly_after_budget_and_control_stop(tmp_path):
    state, work, cp, policy, _, _, _, _, process, backend, git = fixture(tmp_path)
    process.lost_reply = True
    gate = MainIntegration(state, git, policy, backend)
    with pytest.raises(SafetyError):
        gate.deliver(work, cp, cancelled=lambda: False)
    assert process.refs[TARGET] == HEAD
    state.set_metadata("control", "stopped")
    backend.deadline = time.time() - 1
    assert gate.reconcile(work, cp)["main_head"] == HEAD
    assert sum("POST" in args for args, _ in process.calls) == 1


def test_stop_during_protection_observation_prevents_post(tmp_path, monkeypatch):
    state, work, cp, policy, _, _, _, _, process, backend, git = fixture(tmp_path)
    original = process.run

    def stop(args, *a, **kw):
        result = original(args, *a, **kw)
        if args[-1].endswith("/branches/main/protection"):
            state.set_metadata("control", "stopped")
        return result

    monkeypatch.setattr(process, "run", stop)
    with pytest.raises(SafetyError):
        MainIntegration(state, git, policy, backend).deliver(work, cp, cancelled=lambda: False)
    assert not any("POST" in args for args, _ in process.calls)


def test_adapter_requires_durable_reservation_before_any_mutation(tmp_path):
    *_, process, backend, _ = fixture(tmp_path)
    with pytest.raises(SafetyError):
        backend.update_refs(BEFORE, HEAD)
    assert process.calls == []


@pytest.mark.parametrize("change", ["total", "duplicate"])
def test_pagination_rejects_inconsistent_second_page(tmp_path, monkeypatch, change):
    *_, backend, _ = fixture(tmp_path)

    def api(endpoint):
        page = int(parse_qs(urlsplit(endpoint).query)["page"][0])
        if page == 1:
            return {"total_count": 101, "items": [{"id": i} for i in range(100)]}
        return {
            "total_count": 102 if change == "total" else 101,
            "items": [{"id": 0 if change == "duplicate" else 100}],
        }

    monkeypatch.setattr(backend, "_api", api)
    with pytest.raises(SafetyError):
        backend._pages("synthetic", "items")


def test_process_offline_marker_change_rejected_before_process_call(tmp_path):
    *_, process, backend, _ = fixture(tmp_path)
    process.offline = False
    with pytest.raises(SafetyError, match="expired or changed"):
        backend._api("synthetic")
    assert process.calls == []


def test_expired_observation_window_cannot_be_restarted(tmp_path, monkeypatch):
    *_, process, backend, _ = fixture(tmp_path)
    backend.deadline = time.time() - 1
    backend.observation_deadline = time.time() - 1
    monkeypatch.setattr(backend, "_intent", lambda *args: {"phase": "update_reserved"})
    with pytest.raises(SafetyError, match="expired or changed"):
        backend._api("synthetic")
    assert process.calls == []
