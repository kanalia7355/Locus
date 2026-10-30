"""Documented CLI adapter; live use requires a proven executor boundary."""

import json
import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from loop_engine.models import Task, check_result
from loop_engine.planning import bounded_json
from loop_engine.process import ProcessRunner
from loop_engine.schemas import SCHEMAS, validate
from loop_engine.security import SafetyError, create_text, reject_secrets


class Boundary(Protocol):
    def require(self, workspace: Path, control_root: Path) -> None: ...
    def command(self, argv: list[str], workspace: Path) -> list[str]: ...


class UnprovenBoundary:
    def require(self, workspace: Path, control_root: Path) -> None:
        raise SafetyError("Complete filesystem/network/tool/lifetime isolation is not proven")

    def command(self, argv: list[str], workspace: Path) -> list[str]:
        raise SafetyError("Sandbox verification unavailable; host fallback forbidden")


class CodexRunner:
    def __init__(
        self, root: Path, *, boundary: Boundary | None = None, process: ProcessRunner | None = None
    ) -> None:
        self.root = root
        self.boundary = boundary or UnprovenBoundary()
        self.process = process or ProcessRunner()

    def invoke(
        self,
        schema: str,
        prompt: dict[str, Any],
        workspace: Path,
        *,
        readonly: bool,
        timeout: float,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> dict[str, Any]:
        self.boundary.require(workspace, self.root)
        deadline = time.monotonic() + timeout

        def remaining() -> float:
            if cancelled() or time.monotonic() >= deadline:
                raise SafetyError("Codex invocation cancelled or deadline exceeded")
            return deadline - time.monotonic()

        reject_secrets(prompt)
        binary = shutil.which("codex.cmd") or shutil.which("codex")
        if not binary:
            raise SafetyError("Codex CLI is unavailable")
        version = self.process.run(
            self.boundary.command([binary, "--version"], workspace),
            workspace,
            timeout=min(15, remaining()),
            cancelled=cancelled,
        )
        auth = self.process.run(
            self.boundary.command([binary, "login", "status"], workspace),
            workspace,
            timeout=min(15, remaining()),
            cancelled=cancelled,
            model=True,
        )
        if version.returncode != 0 or auth.returncode != 0:
            raise SafetyError("CLI version/authentication unavailable")
        schema_path = self.root / ".loop/runtime/contracts" / f"{schema}.schema.json"
        create_text(schema_path, json.dumps(SCHEMAS[schema]))
        if json.loads(schema_path.read_text(encoding="utf-8")) != SCHEMAS[schema]:
            raise SafetyError("Structured contract file changed")
        argv = [
            binary,
            "exec",
            "--json",
            "--ephemeral",
            "--sandbox",
            "read-only" if readonly else "workspace-write",
            "--disable",
            "multi_agent",
            "--disable",
            "apps",
            "--disable",
            "plugins",
            "-c",
            'approval_policy="never"',
            "-c",
            "sandbox_workspace_write.network_access=false",
            "-c",
            'web_search="disabled"',
            "-c",
            'shell_environment_policy.inherit="none"',
            "--cd",
            str(workspace),
            "--output-schema",
            str(schema_path),
            "-",
        ]
        # Never --yolo, danger-full-access, ignore-rules, hook bypass, or session resume.
        outcome = self.process.run(
            self.boundary.command(argv, workspace),
            workspace,
            timeout=remaining(),
            stdin=json.dumps(prompt, ensure_ascii=False),
            cancelled=cancelled,
            model=True,
        )
        if outcome.outcome != "exit" or outcome.returncode != 0:
            raise SafetyError(f"Codex execution did not finish successfully: {outcome.outcome}")
        final: str | None = None
        for line in outcome.stdout.splitlines():
            event = bounded_json(line)
            if event.get("type") in {"turn.failed", "error"}:
                raise SafetyError("Codex emitted a failed turn")
            item = event.get("item", {})
            if event.get("type") == "item.completed" and item.get("type") == "agent_message":
                final = item.get("text")
        if not isinstance(final, str):
            raise SafetyError("No final structured agent response")
        result = bounded_json(final)
        validate(schema, result)
        return result  # type: ignore[no-any-return]

    def execute(
        self,
        task: Task,
        context: dict[str, Any],
        workspace: Path,
        *,
        timeout: float,
        cancelled: Callable[[], bool],
    ) -> dict[str, Any]:
        prompt = {
            "role": "sole worker; no subagents, commits, approvals or remote operations",
            "task": task.document(),
            "context": context,
            "instruction": "Inspect code; implement scope; return schema; preserve acceptance.",
        }
        result = self.invoke(
            "result", prompt, workspace, readonly=False, timeout=timeout, cancelled=cancelled
        )
        check_result(task, result)
        return result

    def plan(self, context: dict[str, Any], root: Path) -> dict[str, Any]:
        return self.invoke(
            "plan",
            {"role": "read-only planner", "immutable_context": context},
            root,
            readonly=True,
            timeout=300,
        )
