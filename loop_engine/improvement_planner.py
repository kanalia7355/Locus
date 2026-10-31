"""Atomic additive task planning; immutable Goal and attempted task scopes survive."""

import json
import time
from dataclasses import replace
from typing import Any
from uuid import uuid4

from loop_engine.models import Task, validate_graph
from loop_engine.security import SafetyError, allowed, fingerprint, protected
from loop_engine.state_store import StateStore

PRIORITY = {"critical": 100, "high": 90, "medium": 60, "low": 30}


class ImprovementPlanner:
    def __init__(self, state: StateStore, allowed_paths: list[str], profile: str) -> None:
        self.state, self.allowed_paths, self.profile = state, allowed_paths, profile

    def apply(
        self, gaps: list[dict[str, Any]], *, head: str, spec_hash: str, receipt: dict[str, Any]
    ) -> list[Task]:
        state = self.state
        binding = spec_hash + ":" + head
        with state.transaction() as db:
            if state.metadata("spec_hash") != spec_hash:
                raise SafetyError("Immutable Goal changed before additive planning")
            goal = db.execute("SELECT id FROM goals WHERE spec_hash=?", (spec_hash,)).fetchall()
            if len(goal) != 1:
                raise SafetyError("A single imported, approved Goal is required")
            tasks = {row["id"]: state._task(row) for row in db.execute("SELECT * FROM tasks")}
            known = {
                row["identity"]: row["task_id"]
                for row in db.execute("SELECT identity,task_id FROM development_findings")
            }
            number = max([int(identifier[5:]) for identifier in tasks] or [0])
            mapping = {}
            new: set[str] = set()
            for gap in gaps:
                if gap["identity"] in known:
                    identifier = known[gap["identity"]]
                else:
                    number += 1
                    if number > 999999:
                        raise SafetyError("Task ID limit reached")
                    identifier = f"TASK-{number:03}"
                    new.add(identifier)
                mapping[gap["key"]] = identifier
            changed = []
            risk_floors = state.metadata("development_risk_floor", {})
            for gap in gaps:
                identifier = mapping[gap["key"]]
                high = (
                    gap["category"] in {"security", "architecture", "scope"}
                    or gap["severity"] in {"critical", "high"}
                    or any(
                        protected(path) or not allowed(path, self.allowed_paths)
                        for path in gap["allowed_paths"]
                    )
                )
                proposed_risk = "high" if high else "low" if gap["severity"] == "low" else "medium"
                ranks = {"low": 0, "medium": 1, "high": 2}
                risk_floors[identifier] = max(
                    (risk_floors.get(identifier, "low"), proposed_risk), key=ranks.__getitem__
                )
                deps = []
                for dependency in gap["depends_on"]:
                    target = mapping.get(dependency, dependency)
                    if target not in tasks and target not in new:
                        raise SafetyError("Improvement dependency is unknown")
                    deps.append(target)
                if identifier in new:
                    work = Task(
                        id=identifier,
                        title=gap["title"],
                        acceptance_criteria=gap["acceptance"],
                        verification_profile=self.profile,
                        allowed_paths=gap["allowed_paths"],
                        status="ready",
                        priority=PRIORITY[gap["severity"]],
                        dependencies=deps,
                        risk_level=proposed_risk,
                        requires_approval=high,
                    )
                else:
                    work = tasks[identifier]
                    # Only untouched, unapproved ready work can be rescheduled. Never
                    # replace acceptance/scope or revive exhausted/completed tasks.
                    has_decision = db.execute(
                        "SELECT 1 FROM decisions WHERE task_id=?", (identifier,)
                    ).fetchone()
                    escalation = {"low": 0, "medium": 1, "high": 2}[proposed_risk] > {
                        "low": 0,
                        "medium": 1,
                        "high": 2,
                    }[work.risk_level]
                    scope_change = (
                        set(gap["allowed_paths"]) != set(work.allowed_paths)
                        or gap["acceptance"] != work.acceptance_criteria
                    )
                    if scope_change or (
                        escalation
                        and (
                            work.attempts or has_decision or work.status not in {"ready", "planned"}
                        )
                    ):
                        target = fingerprint(
                            {
                                "spec": spec_hash,
                                "head": head,
                                "gap": gap,
                                "task": work.specification_hash(),
                            }
                        )
                        decision = {
                            "id": "DEC-" + uuid4().hex[:16],
                            "task_id": identifier,
                            "category": "scope",
                            "risk": "high",
                            "question": "Risk or proposed task scope changed. Assess updated "
                            "evidence before continuing. Attempts and scope remain fixed.",
                            "options": ["approve", "reject", "revise"],
                            "status": "pending",
                            "blocking_tasks": [identifier],
                            "target_hash": target,
                        }
                        if not db.execute(
                            "SELECT 1 FROM decisions WHERE task_id=? AND category='scope' "
                            "AND target_hash=?",
                            (identifier, target),
                        ).fetchone():
                            db.execute(
                                "INSERT INTO decisions VALUES "
                                "(?,?,?,?,?,'pending',NULL,NULL,NULL,?)",
                                (
                                    decision["id"],
                                    identifier,
                                    "scope",
                                    target,
                                    state.encode(decision),
                                    time.time(),
                                ),
                            )
                            state._event(
                                db,
                                "approval.requested",
                                identifier,
                                {"id": decision["id"], "category": "scope"},
                            )
                        continue
                    if work.attempts or work.status not in {"ready", "planned"} or has_decision:
                        continue
                    work = replace(
                        work,
                        priority=PRIORITY[gap["severity"]],
                        dependencies=sorted(set(deps)),
                        version=work.version + 1,
                        risk_level=proposed_risk if escalation else work.risk_level,
                        requires_approval=work.requires_approval or high,
                    )
                tasks[identifier] = work
                changed.append(work)
            validate_graph(list(tasks.values()))
            for work in changed:
                if work.id in new:
                    db.execute(
                        "INSERT INTO tasks VALUES (?,?,?,?,?,0,0,?)",
                        (
                            work.id,
                            goal[0]["id"],
                            state.encode(work.document()),
                            work.specification_hash(),
                            work.status,
                            time.time(),
                        ),
                    )
                else:
                    db.execute(
                        "UPDATE tasks SET document=?,spec_hash=?,version=?,updated=? WHERE id=?",
                        (
                            state.encode(work.document()),
                            work.specification_hash(),
                            work.version,
                            time.time(),
                            work.id,
                        ),
                    )
                    db.execute("DELETE FROM task_dependencies WHERE task_id=?", (work.id,))
            for work in changed:
                for dependency in work.dependencies:
                    db.execute("INSERT INTO task_dependencies VALUES (?,?)", (work.id, dependency))
            for gap in gaps:
                db.execute(
                    "INSERT INTO development_findings VALUES (?,?,?,?,?) ON CONFLICT(identity) "
                    "DO UPDATE SET last_head=excluded.last_head,document=excluded.document",
                    (gap["identity"], mapping[gap["key"]], head, head, state.encode(gap)),
                )
            db.execute(
                "INSERT INTO development_evaluations VALUES (?,?,?,?) ON CONFLICT(binding) "
                "DO UPDATE SET document=excluded.document,created=excluded.created",
                (binding, head, state.encode(receipt), time.time()),
            )
            db.execute(
                "INSERT INTO development_observations(binding,head,document,created) "
                "VALUES (?,?,?,?)",
                (binding, head, state.encode(receipt), time.time()),
            )
            db.execute(
                "INSERT INTO metadata VALUES ('development_progress',?) ON CONFLICT(key) "
                "DO UPDATE SET value=excluded.value",
                (state.encode(receipt["progress"]),),
            )
            db.execute(
                "INSERT INTO metadata VALUES ('development_risk_floor',?) ON CONFLICT(key) "
                "DO UPDATE SET value=excluded.value",
                (state.encode(risk_floors),),
            )
            state._event(
                db, "development.evaluated", None, {"head": head, "new_tasks": sorted(new)}
            )
            return [tasks[identifier] for identifier in sorted(new)]

    def receipt(self, spec_hash: str, head: str) -> dict[str, Any] | None:
        with self.state.connect() as db:
            row = db.execute(
                "SELECT document FROM development_evaluations WHERE binding=?",
                (spec_hash + ":" + head,),
            ).fetchone()
            return json.loads(row[0]) if row else None
