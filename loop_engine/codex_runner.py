"""Documented CLI adapter; live use requires a proven executor boundary."""

import json
import shutil
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from loop_engine.models import Task, check_result
from loop_engine.planning import bounded_json
from loop_engine.process import ProcessRunner
from loop_engine.schemas import SCHEMAS, validate
from loop_engine.security import SafetyError, create_text, fingerprint, reject_secrets


def transport_schema(value: Any) -> Any:
    """The service rejects uniqueItems; keep it mandatory in local validation."""
    if isinstance(value, dict):
        return {key: transport_schema(item) for key, item in value.items() if key != "uniqueItems"}
    if isinstance(value, list):
        return [transport_schema(item) for item in value]
    return value


def codex_binary(root: Path | None = None) -> str | None:
    """Prefer the installed native Windows binary over cmd.exe argument rewriting."""
    project = (root or Path.cwd()).resolve()
    receipt = project / ".loop/runtime/codex-client.json"
    if receipt.is_file():
        import hashlib

        value = json.loads(receipt.read_text(encoding="utf-8"))
        native = project / value["relative_binary"]
        if (
            not native.resolve().is_relative_to(project / ".loop/runtime/codex-client")
            or hashlib.sha256(native.read_bytes()).hexdigest() != value["sha256"]
        ):
            raise SafetyError("Project Codex binary identity changed")
        return str(native)
    launcher = shutil.which("codex.cmd") or shutil.which("codex")
    if launcher and sys.platform == "win32":
        native = Path(launcher).parent / (
            "node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/"
            "vendor/x86_64-pc-windows-msvc/bin/codex.exe"
        )
        if native.is_file():
            return str(native)
    return launcher


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
        deadline = time.monotonic() + timeout

        def remaining() -> float:
            if cancelled() or time.monotonic() >= deadline:
                raise SafetyError("Codex invocation cancelled or deadline exceeded")
            return deadline - time.monotonic()

        if getattr(self.boundary, "file_proposals", False):
            self.boundary.probe(workspace, timeout=remaining(), cancelled=cancelled)  # type: ignore[attr-defined]
        self.boundary.require(workspace, self.root)

        reject_secrets(prompt)
        binary = codex_binary(self.root)
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
        wire_schema = transport_schema(SCHEMAS[schema])
        schema_path = (
            self.root
            / ".loop/runtime/contracts"
            / f"{schema}-{fingerprint(wire_schema)}.schema.json"
        )
        create_text(schema_path, json.dumps(wire_schema))
        if json.loads(schema_path.read_text(encoding="utf-8")) != wire_schema:
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
            from loop_engine.checks import sanitized
            from loop_engine.security import atomic_text

            failures = []
            event_types = []
            final_seen = False
            for line in outcome.stdout.splitlines():
                try:
                    event = bounded_json(line)
                    event_types.append(str(event.get("type", "unknown")))
                    final_seen = final_seen or (
                        event.get("type") == "item.completed"
                        and event.get("item", {}).get("type") == "agent_message"
                    )
                    if event.get("type") in {"turn.failed", "error"}:
                        failures.append(
                            sanitized(str(event.get("error", event.get("message", ""))))
                        )
                except ValueError:
                    continue
            atomic_text(
                self.root / ".loop/runtime/codex-failure.json",
                json.dumps(
                    {
                        "outcome": outcome.outcome,
                        "exit_code": outcome.returncode,
                        "diagnostic": sanitized(outcome.stderr, 3000),
                        "errors": failures,
                        "event_types": event_types,
                        "final_response_seen": final_seen,
                    }
                ),
            )
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
        self.boundary.require(workspace, self.root)
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
        if getattr(self.boundary, "file_proposals", False):
            from loop_engine.proposals import apply_proposal, source_bundle

            prompt["source_files"] = source_bundle(task, workspace)
            prompt["instruction"] = (
                "No tools are available. Return exact text edits in proposal schema. "
                "old=null creates a new file; otherwise old must occur exactly once. "
                "No deletions, control-plane changes, commits, approvals or remote operations. "
                "Preserve Goal and tests; files_changed must match edits exactly. "
                "Return blocked if supplied source is insufficient."
            )
            proposal = self.invoke(
                "proposal", prompt, workspace, readonly=True, timeout=timeout, cancelled=cancelled
            )
            if cancelled():
                raise SafetyError("Proposal application cancelled")
            self.boundary.require(workspace, self.root)
            return apply_proposal(task, workspace, proposal)
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
