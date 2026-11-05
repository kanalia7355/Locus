"""Bounded run and exact per-call bindings in the existing Controller/StateStore."""

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from loop_engine.approval import ApprovalQueue
from loop_engine.config import load
from loop_engine.git_manager import GitManager
from loop_engine.planning import source_snapshot
from loop_engine.security import SafetyError, allowed, fingerprint, reparse, sensitive, within
from loop_engine.state_store import StateStore

VERSION = "c-min-bounded-run-v1"
# Public approved offline design, never a live/run authorization by itself.
# pragma: allowlist nextline secret
APPROVAL = "f52797bbc096c7c00d2ffd8c5d6d07e0da4928511c6b7758c44602a3e80b0f04"
AUTH = "official-client-use-and-standard-refresh-of-existing-chatgpt-profile"
PATHS = ["backend", "frontend", "tests"]
ROLES = {"worker": "proposal", "reviewer": "review", "evaluator": "evaluation"}


def fail(condition: bool, message: str) -> None:
    if not condition:
        raise SafetyError(message)


def files(root: Path, git: GitManager, *, control_only: bool) -> str:
    names = git._git(["ls-files", "-z"], root).split("\0")
    if control_only:
        # Git's immutable blob/mode identity handles approved LF/CRLF checkout
        # normalization. Explicitly reject dirty control source before using it.
        changed = git._git(
            ["diff", "--no-ext-diff", "--no-textconv", "--name-only", "-z", "HEAD", "--"], root
        ).split("\0")
        fail(all(allowed(name, PATHS) for name in changed if name), "Dirty control-plane source")
        tree = {}
        for entry in git._git(["ls-tree", "-r", "-z", "HEAD"], root).split("\0"):
            if entry:
                metadata, name = entry.split("\t", 1)
                if not allowed(name, PATHS):
                    fail(not sensitive(name), "Sensitive control source rejected")
                    tree[name] = metadata
        return fingerprint(tree)
    if not control_only:
        names += git._git(["ls-files", "--others", "--exclude-standard", "-z"], root).split("\0")
    hashes = {}
    for name in sorted(set(filter(None, names))):
        if control_only and allowed(name, PATHS):
            continue
        fail(not sensitive(name), "Sensitive file cannot be a source binding")
        path = within(root, name)
        fail(path.is_file(), "Source object missing")
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return fingerprint(hashes)


def identity(root: Path, state: StateStore) -> dict[str, Any]:
    from loop_engine.c_min_runtime import verify_profile
    from loop_engine.runtime_diagnostics import runtime_identity

    config = load(root / ".loop/config.yaml")
    fail(
        not state.metadata("policy_migration_pending")
        and not state.metadata("orphan_uncertainty", False),
        "Unsettled control policy or lifetime",
    )
    fail(
        config["github"]["delivery"] == "local_commit_push"
        and config["security"]["allow_model_execution"] is True
        and config["security"]["sandbox_executor"] == "proposal-docker"
        and config["github"]["base"] == "loop/local-development"
        and config["github"]["remote"] == "origin"
        and config["github"]["auto_merge"] == "off"
        and sorted(config["development"]["allowed_paths"]) == PATHS,
        "Exact approved local-development policy required",
    )
    spec = fingerprint(source_snapshot(root))
    fail(spec == state.metadata("spec_hash"), "Source specification changed")
    from loop_engine.docker_boundary import image_audit_evidence

    qa = json.loads((root / ".loop/runtime/qa-image.json").read_text())
    fail(image_audit_evidence(root, qa.get("image_id"), root), "Current QA image audit required")
    verify_profile(state)
    git = GitManager(root, state)
    git._safe_configuration()
    repository = config["github"]["repository"]
    permitted = {
        f"https://github.com/{repository}",
        f"https://github.com/{repository}.git",
        f"git@github.com:{repository}.git",
    }
    urls = [
        git._git(["remote", "get-url", "--all", "origin"]),
        git._git(["remote", "get-url", "--push", "--all", "origin"]),
    ]
    fail(all(url in permitted for url in urls), "Repository origin changed")
    fail(
        git._git(["symbolic-ref", "--short", "HEAD"]) == "loop/local-development",
        "Integration checkout changed",
    )
    fail(
        not git._git(["status", "--porcelain", "--untracked-files=all"]),
        "Integration source must be clean",
    )
    return {
        "root": str(root.resolve()),
        "repository": repository,
        "origin": urls,
        "common": git._git(["rev-parse", "--path-format=absolute", "--git-common-dir"]),
        "spec": spec,
        "config": fingerprint(config),
        "runtime": runtime_identity(root),
        "profile": fingerprint(state.metadata("c_min_auth_profile")),
        "control": files(root, git, control_only=True),
        "model": "gpt-6.1-sol",
        "branch": "loop/local-development",
        "paths": PATHS,
        "roles": ROLES,
    }


def unsettled(db: Any) -> bool:
    if db.execute("SELECT 1 FROM executions WHERE status='running'").fetchone():
        return True
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='model_invocations'").fetchone():
        return (
            db.execute("SELECT 1 FROM model_invocations WHERE phase!='completed'").fetchone()
            is not None
        )
    return False


def prepare(
    root: Path, state: StateStore, duration: float, *, start_window: float = 180
) -> dict[str, Any]:
    fail(duration == 1800 and 0 < start_window <= 1800, "Approved thirty-minute window required")
    fail(
        duration <= load(root / ".loop/config.yaml")["loop"]["max_runtime_minutes"] * 60,
        "Configured runtime ceiling cannot be exceeded",
    )
    fail(
        state.metadata("control") == "stopped" and not state.metadata("orphan_uncertainty", False),
        "Stopped, settled Controller required",
    )
    fail(state.metadata("c_min_live_permit") is None, "Legacy permit must be reconciled explicitly")
    current = identity(root, state)
    git = GitManager(root, state)
    head = git._git(["rev-parse", "refs/heads/loop/local-development^{commit}"])
    with state.transaction() as db:
        fail(not unsettled(db), "Unsettled invocation prevents new run preparation")
        row = db.execute("SELECT value FROM metadata WHERE key='c_min_run_proposal'").fetchone()
        if row:
            existing = json.loads(row[0])
            fail(
                existing["identity"] == current
                and existing["start_head"] == head
                and existing["duration"] == duration
                and time.time() < existing["start_until"],
                "Existing run proposal requires explicit reconciliation",
            )
            scope = dict(existing)
        else:
            now = time.time()
            scope = {
                "version": VERSION,
                "approval": APPROVAL,
                "id": uuid4().hex,
                "identity": current,
                "start_head": head,
                "duration": duration,
                "not_before": now,
                "start_until": now + start_window,
                "latest_deadline": now + start_window + duration,
                "auth": AUTH,
            }
            db.execute(
                "INSERT INTO c_min_runs VALUES (?,?,NULL,NULL)", (scope["id"], state.encode(scope))
            )
            db.execute(
                "INSERT INTO metadata VALUES ('c_min_run_proposal',?)", (state.encode(scope),)
            )
            state._event(
                db, "run.prepared", None, {"run": scope["id"], "scope": fingerprint(scope)}
            )
    ApprovalQueue(state).request(
        None,
        "scope",
        fingerprint(scope),
        "Approve this exact finite normal run, official CLI credential use/standard refresh, "
        "and per-call Controller-derived bindings? This is not an offline design approval.",
        "high",
    )
    return scope


def scope_for(root: Path, state: StateStore, *, running: bool) -> dict[str, Any]:
    scope = state.metadata("c_min_run_proposal")
    fail(state.metadata("c_min_live_permit") is None, "Ambiguous legacy and delegated permissions")
    fail(
        isinstance(scope, dict)
        and set(scope)
        == {
            "version",
            "approval",
            "id",
            "identity",
            "start_head",
            "duration",
            "not_before",
            "start_until",
            "latest_deadline",
            "auth",
        },
        "Exact prepared run required",
    )
    fail(
        scope["version"] == VERSION
        and scope["approval"] == APPROVAL
        and scope["auth"] == AUTH
        and scope["duration"] == 1800
        and scope["not_before"] <= time.time()
        and 0 < scope["start_until"] - scope["not_before"] <= 1800
        and scope["latest_deadline"] == scope["start_until"] + scope["duration"],
        "Run scope format/window rejected",
    )
    fail(scope["identity"] == identity(root, state), "Immutable run identity changed")
    fail(
        ApprovalQueue(state).status(None, "scope", fingerprint(scope)) == "approved",
        "Explicit live run/credential authorization required",
    )
    with state.connect() as db:
        row = db.execute("SELECT * FROM c_min_runs WHERE id=?", (scope["id"],)).fetchone()
    fail(row is not None and json.loads(row["document"]) == scope, "Prepared run record changed")
    if running:
        budget = state.metadata("run_budget", {})
        fail(
            state.metadata("control") == "running"
            and row["started"] is not None
            and budget.get("id") == scope["id"]
            and budget.get("deadline") == row["deadline"]
            and time.time() < row["deadline"] <= scope["latest_deadline"],
            "Owning run is not active or deadline changed",
        )
    elif row["started"] is None:
        fail(time.time() < scope["start_until"], "Run start window expired")
    else:
        fail(time.time() < row["deadline"], "Existing run deadline expired")
    return dict(scope)


def adopt(root: Path, state: StateStore, *, resume: bool, duration: float | None) -> dict[str, Any]:
    from loop_engine.runtime_diagnostics import require_receipt

    scope = scope_for(root, state, running=False)
    fail(
        scope["duration"] <= load(root / ".loop/config.yaml")["loop"]["max_runtime_minutes"] * 60,
        "Configured runtime ceiling changed",
    )
    require_receipt(root)  # Trial evidence cannot replace this existing normal gate.
    fail(duration is None or duration == scope["duration"], "Run duration differs from grant")
    with state.transaction() as db:
        fail(not unsettled(db), "Run start requires settled prior calls")
        row = db.execute("SELECT * FROM c_min_runs WHERE id=?", (scope["id"],)).fetchone()
        old = db.execute("SELECT value FROM metadata WHERE key='run_budget'").fetchone()
        prior = json.loads(old[0]) if old else {}
        if row["started"] is not None:
            fail(
                resume
                and prior.get("id") == scope["id"]
                and prior.get("deadline") == row["deadline"],
                "Run cannot be restarted or extended",
            )
            return dict(prior)
        fail(not resume, "Prepared new run is not a resume window")
        now = time.time()
        fail(now < scope["start_until"], "Run start expired before adoption")
        budget = {
            "id": scope["id"],
            "started": now,
            "deadline": now + scope["duration"],
            "tasks": [],
        }
        db.execute(
            "UPDATE c_min_runs SET started=?,deadline=? WHERE id=? AND started IS NULL",
            (now, budget["deadline"], scope["id"]),
        )
        db.execute(
            "INSERT INTO metadata VALUES ('run_budget',?) ON CONFLICT(key) "
            "DO UPDATE SET value=excluded.value",
            (state.encode(budget),),
        )
        state._event(db, "run.adopted", None, {"run": scope["id"], "previous_budget": prior})
    return budget


def call_binding(
    root: Path, state: StateStore, workspace: Path, owner: dict[str, Any], artifact: str
) -> dict[str, Any]:
    from loop_engine.codex_runner import transport_schema
    from loop_engine.schemas import SCHEMAS

    scope = scope_for(root, state, running=True)
    fail(
        owner.get("role") in ROLES
        and owner.get("schema") == ROLES[owner["role"]]
        and owner.get("spec") == scope["identity"]["spec"],
        "Call role/schema/spec changed",
    )
    fail(not any(reparse(p) for p in (workspace, *workspace.parents)), "Workspace reparse boundary")
    git = GitManager(root, state)
    integrated = git._git(["rev-parse", "refs/heads/loop/local-development^{commit}"])
    git._git(["merge-base", "--is-ancestor", scope["start_head"], integrated])
    fail(
        integrated == scope["start_head"] or integrated == state.metadata("local_published_head"),
        "Unconfirmed integrated HEAD advancement",
    )
    common = git._git(["rev-parse", "--path-format=absolute", "--git-common-dir"], workspace)
    fail(
        common == scope["identity"]["common"]
        and Path(git._git(["rev-parse", "--show-toplevel"], workspace)).resolve()
        == workspace.resolve(),
        "Foreign or unexpected source worktree",
    )
    head = git._git(["rev-parse", "HEAD"], workspace)
    config = load(root / ".loop/config.yaml")
    if owner["role"] == "evaluator":
        with state.connect() as db:
            busy = db.execute(
                "SELECT 1 FROM tasks WHERE status IN ('running','verifying','reviewing')"
            ).fetchone()
        fail(busy is None, "Project evaluation overlaps an active task")
        usage = state.metadata("development_budget", {})
        fail(
            usage.get("run") == scope["id"]
            and usage.get("cycles") == owner["attempt"]
            and 1
            <= owner["attempt"]
            <= load(root / ".loop/config.yaml")["development"]["max_cycles_per_run"]
            and owner["owner_id"] == scope["id"] + ":" + str(owner["attempt"])
            and owner["binding"] == owner["spec"] + ":" + integrated
            and workspace == within(root, ".loop/runtime/evaluations/" + integrated)
            and head == integrated
            and not git._git(["status", "--porcelain"], workspace),
            "Evaluation owner/workspace changed",
        )
        fail(type(usage.get("started")) in {float, int}, "Evaluation phase start missing")
        phase_deadline = usage["started"] + config["development"]["evaluation_timeout_minutes"] * 60
    else:
        with state.connect() as db:
            execution = db.execute(
                "SELECT * FROM executions WHERE id=?", (owner["owner_id"],)
            ).fetchone()
        fail(
            execution is not None
            and execution["run_id"] == scope["id"]
            and execution["kind"] == "worker"
            and execution["attempt"] == owner["attempt"],
            "Execution owner changed",
        )
        task = state.task(execution["task_id"])
        with state.connect() as db:
            busy = db.execute(
                "SELECT id FROM tasks WHERE status IN ('running','verifying','reviewing')"
            ).fetchall()
        fail({row[0] for row in busy} == {task.id}, "Concurrent task scope rejected")
        tasks = state.metadata("run_budget", {}).get("tasks", [])
        fail(
            task.id in tasks
            and len(set(tasks)) == len(tasks)
            and len(tasks) <= config["loop"]["max_tasks_per_run"],
            "Controller task budget changed",
        )
        checkpoint = state.get_checkpoint(task.id)
        fail(
            1
            <= task.attempts
            == owner["attempt"]
            <= min(
                3,
                task.max_attempts,
                load(root / ".loop/config.yaml")["loop"]["max_attempts_per_task"],
            )
            and all(allowed(path, PATHS) for path in task.allowed_paths)
            and workspace == within(root, ".loop/runtime/worktrees/" + task.id)
            and str(workspace) == checkpoint.get("workspace")
            and head == checkpoint.get("base")
            and git._git(["symbolic-ref", "--short", "HEAD"], workspace) == checkpoint.get("branch")
            and task.status == ("running" if owner["role"] == "worker" else "reviewing")
            and execution["status"] == ("running" if owner["role"] == "worker" else "returned"),
            "Task/execution/path/attempt ownership changed",
        )
        snapshot = git.snapshot(task, workspace)
        if owner["role"] == "worker":
            expected = fingerprint(
                {
                    "task": task.specification_hash(),
                    "source": fingerprint(snapshot),
                    "base": checkpoint["base"],
                }
            )
        else:
            with state.connect() as db:
                evidence = db.execute(
                    "SELECT document FROM verification_results WHERE execution_id=? "
                    "ORDER BY created DESC LIMIT 1",
                    (owner["owner_id"],),
                ).fetchone()
            fail(evidence is not None, "Review verification evidence missing")
            verification = json.loads(evidence[0])
            fail(verification.get("passed") is True, "Review requires passing verification")
            expected = fingerprint(
                {
                    "task": task.specification_hash(),
                    "source_specification": owner["spec"],
                    "snapshot": snapshot,
                    "verification": verification,
                }
            )
        fail(owner["binding"] == expected, "Source/evidence owner binding differs")
        phase_deadline = execution["started"] + config["loop"]["task_timeout_minutes"] * 60
    fail(
        files(workspace, git, control_only=True) == scope["identity"]["control"],
        "Worktree control-plane source changed",
    )
    fail(time.time() < phase_deadline, "Owning phase deadline expired")
    return {
        "scope": fingerprint(scope),
        "run": scope["id"],
        "owner": owner,
        "schema": fingerprint(transport_schema(SCHEMAS[owner["schema"]])),
        "workspace": str(workspace),
        "artifact": artifact,
        "integrated_head": integrated,
        "workspace_head": head,
        "source": files(workspace, git, control_only=False),
        "run_deadline": state.metadata("run_budget")["deadline"],
        "call_deadline": min(phase_deadline, state.metadata("run_budget")["deadline"]),
    }


def reserve_binding(state: StateStore, invocation: str, binding: dict[str, Any]) -> None:
    with state.transaction() as db:
        row = db.execute("SELECT * FROM model_invocations WHERE id=?", (invocation,)).fetchone()
        fail(
            row is not None
            and row["phase"] == "prepared"
            and json.loads(row["owner"]) == binding["owner"]
            and row["artifact"] == binding["artifact"],
            "Call reservation differs",
        )
        old = db.execute(
            "SELECT document FROM model_run_bindings WHERE invocation=?", (invocation,)
        ).fetchone()
        if old:
            fail(json.loads(old[0]) == binding, "Existing call binding changed")
            return
        db.execute(
            "INSERT INTO model_run_bindings VALUES (?,?,?,?)",
            (invocation, binding["run"], state.encode(binding), time.time()),
        )
        state._event(
            db, "model.run_bound", None, {"invocation": invocation, "binding": fingerprint(binding)}
        )


def recheck(
    state: StateStore, invocation: str, expected: dict[str, Any], *, deadline: float | None = None
) -> None:
    with state.connect() as db:
        row = db.execute(
            "SELECT document FROM model_run_bindings WHERE invocation=?", (invocation,)
        ).fetchone()
    fail(row is not None and json.loads(row[0]) == expected, "Durable call binding changed")
    with state.connect() as db:
        model = db.execute("SELECT * FROM model_invocations WHERE id=?", (invocation,)).fetchone()
    fail(
        model is not None
        and json.loads(model["owner"]) == expected["owner"]
        and model["artifact"] == expected["artifact"]
        and (deadline is None or model["deadline"] == deadline),
        "Model reservation changed",
    )


def active(state: StateStore, binding: dict[str, Any]) -> bool:
    scope = state.metadata("c_min_run_proposal", {})
    budget = state.metadata("run_budget", {})
    return bool(
        state.metadata("control") == "running"
        and fingerprint(scope) == binding["scope"]
        and budget.get("id") == binding["run"]
        and budget.get("deadline") == binding["run_deadline"]
        and time.time() < binding["run_deadline"]
        and time.time() < binding["call_deadline"]
        and ApprovalQueue(state).status(None, "scope", binding["scope"]) == "approved"
    )


def auth_probe_authorized(root: Path) -> bool:
    """Read-only fresh permission check; a receipt is not a credential grant."""
    from loop_engine.runtime_diagnostics import runtime_identity

    path = root / ".loop/runtime/state.sqlite3"
    try:
        if not path.is_file() or any(reparse(p) for p in (path, *path.parents)):
            return False
        state = StateStore(path, readonly=True)
        if state.metadata("c_min_run_proposal") is not None:
            scope_for(root, state, running=False)
            return True
        permit = state.metadata("c_min_live_permit")
        budget = state.metadata("run_budget", {})
        return bool(
            isinstance(permit, dict)
            and set(permit) == {"operation", "runtime", "artifact", "run", "expires"}
            and permit["operation"] == "c-min-normal-development"
            and permit["runtime"] == runtime_identity(root)
            and permit["run"] == budget.get("id")
            and time.time() < permit["expires"] <= budget.get("deadline", 0)
            and ApprovalQueue(state).status(None, "scope", fingerprint(permit)) == "approved"
        )
    except (ValueError, OSError, TypeError, KeyError, sqlite3.Error):
        return False
