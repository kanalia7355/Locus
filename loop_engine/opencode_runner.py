"""OpenCode CLI adapter for bounded, fail-closed task execution.

This runner uses the installed OpenCode CLI in non-interactive mode and is
intended for synthetic, authorized workspaces. It does not grant credentials,
network egress, or provider access.
"""

from __future__ import annotations

import json
import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from loop_engine.models import Task, check_result
from loop_engine.process import ProcessRunner
from loop_engine.schemas import SCHEMAS, validate
from loop_engine.security import SafetyError, reject_secrets

MAX_PROMPT_CHARS = 300_000


class Boundary(Protocol):
    def require(self, workspace: Path, control_root: Path) -> None: ...

    def command(self, argv: list[str], workspace: Path) -> list[str]: ...


class UnprovenBoundary:
    file_proposals = False
    c_min = False

    def require(self, workspace: Path, control_root: Path) -> None:
        raise SafetyError("Execution boundary unavailable")

    def command(self, argv: list[str], workspace: Path) -> list[str]:
        raise SafetyError("Execution boundary unavailable")


class LocalWorkspaceBoundary:
    """Minimal local boundary for synthetic/offline OpenCode execution paths."""

    file_proposals = False
    c_min = False

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def require(self, workspace: Path, control_root: Path) -> None:
        if control_root.resolve() != self.root:
            raise SafetyError("Control-root mismatch")
        resolved = workspace.resolve()
        if not resolved.is_dir():
            raise SafetyError("Workspace unavailable")
        if not (resolved == self.root or resolved.is_relative_to(self.root)):
            raise SafetyError("Workspace outside control root")

    def command(self, argv: list[str], workspace: Path) -> list[str]:
        return argv


class OpenCodeError(SafetyError):
    """Classified OpenCode adapter failure."""

    def __init__(self, message: str, *, category: str) -> None:
        super().__init__(message)
        self.category = category


_QUOTA_PATTERNS = (
    "quota",
    "rate limit",
    "rate_limit",
    "insufficient_quota",
    "exceeded your current quota",
    "free tier",
    "capacity",
)
_AUTH_PATTERNS = ("unauthorized", "authentication", "auth failed", "forbidden", "api key", "login")
_TRANSIENT_PATTERNS = (
    "429",
    "too many requests",
    "temporar",
    "timeout",
    "timed out",
    "connection reset",
)
_TOOL_PATTERNS = (
    "unknown flag",
    "invalid option",
    "unsupported tool",
    "tool not supported",
    "incompatible tool",
    "model does not support tools",
    "tools are not supported",
)


def classify_failure(*, outcome: str, returncode: int | None, stdout: str, stderr: str) -> str:
    text = f"{stdout}\n{stderr}".lower()
    if outcome == "timeout":
        return "timeout"
    if outcome == "cancelled":
        return "cancelled"
    if outcome == "output_limit":
        return "output_limit"
    if outcome not in {"exit"}:
        return "unavailable"
    if returncode == 0:
        return "ok"
    if any(pattern in text for pattern in _QUOTA_PATTERNS):
        return "quota_exhausted"
    if any(pattern in text for pattern in _AUTH_PATTERNS):
        return "auth_failure"
    if any(pattern in text for pattern in _TOOL_PATTERNS):
        return "model_tool_incompatible"
    if any(pattern in text for pattern in _TRANSIENT_PATTERNS):
        return "transient_failure"
    return "execution_failed"


def select_free_model(
    available_models: list[str],
    *,
    preferred: str | None = None,
    allowed_prefix: str = "opencode/",
    free_suffix: str = "-free",
) -> str:
    """Pick an eligible free OpenCode model from a discovered catalog list.

    Only explicit catalog entries are considered; no model IDs are guessed.
    """
    normalized = [model.strip() for model in available_models if model and model.strip()]
    if preferred:
        if preferred in normalized:
            return preferred
        raise OpenCodeError(f"Preferred model unavailable: {preferred}", category="unavailable")
    for model in normalized:
        if model.startswith(allowed_prefix) and model.endswith(free_suffix):
            return model
    raise OpenCodeError("No eligible free OpenCode model available", category="unavailable")


def _looks_like_result(value: Any) -> bool:
    return isinstance(value, dict) and {"task_id", "status"} <= set(value)


def _unwrap_candidate(candidate: Any) -> Any | None:
    if _looks_like_result(candidate):
        return candidate
    if not isinstance(candidate, dict):
        return None
    for key in ("result", "output", "message", "data", "response"):
        value = candidate.get(key)
        if _looks_like_result(value):
            return value
        if isinstance(value, str):
            try:
                inner = json.loads(value)
                if _looks_like_result(inner):
                    return inner
            except json.JSONDecodeError:
                pass
    for key in ("text", "content"):
        value = candidate.get(key)
        if isinstance(value, str):
            try:
                inner = json.loads(value)
                if _looks_like_result(inner):
                    return inner
            except json.JSONDecodeError:
                pass
    return None


def _extract_json(text: str) -> Any:
    stripped = text.strip()
    if not stripped:
        raise OpenCodeError("No output from OpenCode", category="malformed_output")
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, list):
            for candidate in reversed(parsed):
                unwrapped = _unwrap_candidate(candidate)
                if unwrapped is not None:
                    return unwrapped
            for candidate in reversed(parsed):
                if isinstance(candidate, dict):
                    return candidate
        unwrapped = _unwrap_candidate(parsed)
        return unwrapped if unwrapped is not None else parsed
    except json.JSONDecodeError:
        pass

    # JSON-lines/events: collect objects and prefer result-like candidates.
    objects: list[Any] = []
    for line in stripped.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            objects.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if objects:
        for candidate in reversed(objects):
            unwrapped = _unwrap_candidate(candidate)
            if unwrapped is not None:
                return unwrapped
        for candidate in reversed(objects):
            if isinstance(candidate, dict):
                return candidate

    # Fallback: scan balanced JSON object candidates.
    decoder = json.JSONDecoder()
    index = 0
    fallback: Any = None
    while index < len(stripped):
        start = stripped.find("{", index)
        if start == -1:
            break
        try:
            candidate, end = decoder.raw_decode(stripped, start)
        except json.JSONDecodeError:
            index = start + 1
            continue
        unwrapped = _unwrap_candidate(candidate)
        if unwrapped is not None:
            return unwrapped
        if fallback is None and isinstance(candidate, dict):
            fallback = candidate
        index = end
    if fallback is not None:
        return fallback
    raise OpenCodeError("Malformed OpenCode output", category="malformed_output")


def resolve_binary(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    binary = shutil.which("opencode")
    if not binary:
        raise OpenCodeError("OpenCode CLI unavailable", category="unavailable")
    return binary


class OpenCodeRunner:
    """Adapter matching Controller's Worker interface for direct result execution."""

    def __init__(
        self,
        root: Path,
        *,
        boundary: Boundary | None = None,
        process: ProcessRunner | None = None,
        state: Any = None,
        model: str | None = None,
        binary: str | None = None,
        agent: str | None = None,
        fallback_models: list[str] | None = None,
    ) -> None:
        self.root = root
        self.boundary = boundary or UnprovenBoundary()
        self.process = process or ProcessRunner()
        self.state = state
        self.model = model
        self.binary = binary
        self.agent = agent
        self.fallback_models = list(fallback_models or [])
        self.pending_model: Any = None

    def acknowledge(self) -> None:
        self.pending_model = None

    def _build_prompt(self, schema: str, payload: dict[str, Any]) -> str:
        contract = SCHEMAS[schema]
        prompt = {
            **payload,
            "output_contract": {
                "schema_name": schema,
                "json_schema": contract,
                "instruction": (
                    "Return ONLY a single JSON object that satisfies the schema. "
                    "No markdown fences, no prose, no extra keys."
                ),
            },
        }
        return json.dumps(prompt, ensure_ascii=False)

    def _record(self, kind: str, **data: Any) -> None:
        state = getattr(self, "state", None)
        if state is None:
            return
        event = getattr(state, "event", None)
        if callable(event):
            try:
                event(kind, None, **data)
            except Exception:
                return

    def _run_cli(
        self,
        prompt: str,
        workspace: Path,
        *,
        timeout: float,
        cancelled: Callable[[], bool],
        schema: str,
        task_id: str | None = None,
    ) -> Any:
        deadline = time.monotonic() + timeout

        def remaining() -> float:
            if cancelled() or time.monotonic() >= deadline:
                raise OpenCodeError(
                    "OpenCode invocation cancelled or deadline exceeded", category="cancelled"
                )
            return max(0.0, deadline - time.monotonic())

        self.boundary.require(workspace, self.root)
        if len(prompt) > MAX_PROMPT_CHARS:
            self._record(
                "opencode.execution",
                schema=schema,
                task_id=task_id,
                model=self.model,
                status="failed",
                category="unavailable",
                reason="prompt_too_large",
            )
            raise OpenCodeError("OpenCode prompt exceeds bounded size", category="unavailable")
        reject_secrets(prompt)
        binary = resolve_binary(self.binary)
        argv = [binary, "run", "--format", "json"]
        if self.model:
            argv.extend(["--model", self.model])
        if self.agent:
            argv.extend(["--agent", self.agent])
        argv.append("--archived")
        argv.append(prompt)
        argv = self.boundary.command(argv, workspace)

        self._record(
            "opencode.invocation",
            schema=schema,
            task_id=task_id,
            model=self.model,
            binary=binary,
            status="started",
        )
        outcome = self.process.run(
            argv,
            workspace,
            timeout=remaining(),
            cancelled=cancelled,
            model=True,
        )
        category = classify_failure(
            outcome=outcome.outcome,
            returncode=outcome.returncode,
            stdout=outcome.stdout,
            stderr=outcome.stderr,
        )
        if category != "ok":
            self._record(
                "opencode.execution",
                schema=schema,
                task_id=task_id,
                model=self.model,
                status="failed",
                category=category,
                outcome=outcome.outcome,
                returncode=outcome.returncode,
                elapsed=getattr(outcome, "elapsed", None),
            )
            raise OpenCodeError(f"OpenCode execution failed: {category}", category=category)
        parsed = _extract_json(outcome.stdout)
        self._record(
            "opencode.execution",
            schema=schema,
            task_id=task_id,
            model=self.model,
            status="ok",
            category="ok",
            outcome=outcome.outcome,
            returncode=outcome.returncode,
            elapsed=getattr(outcome, "elapsed", None),
        )
        return parsed

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
        if getattr(self.boundary, "file_proposals", False) or getattr(
            self.boundary, "c_min", False
        ):
            raise OpenCodeError(
                "OpenCode adapter does not support proposal/C-min boundaries in this mode",
                category="model_tool_incompatible",
            )
        self.boundary.require(workspace, self.root)
        task_id = None
        task = prompt.get("task")
        if isinstance(task, dict) and isinstance(task.get("id"), str):
            task_id = task.get("id")
        result = self._run_cli(
            self._build_prompt(schema, prompt),
            workspace,
            timeout=timeout,
            cancelled=cancelled,
            schema=schema,
            task_id=task_id,
        )
        if not isinstance(result, dict):
            raise OpenCodeError("OpenCode result is not an object", category="malformed_output")
        reject_secrets(result)
        validate(schema, result)
        self.boundary.require(workspace, self.root)
        return result

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
            "instruction": (
                "Inspect code in the workspace, implement only the task scope, and return a "
                "schema-valid result. Do not claim checks ran unless they actually ran. "
                "Preserve acceptance criteria."
            ),
        }
        if getattr(self.boundary, "file_proposals", False):
            self._record(
                "opencode.execution",
                schema="result",
                task_id=task.id,
                model=self.model,
                status="failed",
                category="model_tool_incompatible",
                reason="file_proposals_unsupported",
            )
            raise OpenCodeError(
                "OpenCode adapter file-proposal mode is not implemented",
                category="model_tool_incompatible",
            )

        models = [self.model] if self.model else [None]
        for candidate in self.fallback_models:
            if candidate not in models:
                models.append(candidate)
        last_error: OpenCodeError | None = None
        for index, model in enumerate(models):
            previous = self.model
            self.model = model
            try:
                result = self.invoke(
                    "result",
                    prompt,
                    workspace,
                    readonly=False,
                    timeout=timeout,
                    cancelled=cancelled,
                )
                check_result(task, result)
                return result
            except OpenCodeError as error:
                last_error = error
                has_next = index + 1 < len(models)
                if has_next and error.category in {
                    "quota_exhausted",
                    "unavailable",
                    "model_tool_incompatible",
                }:
                    self._record(
                        "opencode.fallback",
                        schema="result",
                        task_id=task.id,
                        from_model=model,
                        to_model=models[index + 1],
                        category=error.category,
                        status="retrying",
                    )
                    continue
                raise
            finally:
                if last_error is not None and index + 1 == len(models):
                    self.model = previous
        if last_error is not None:
            raise last_error
        raise OpenCodeError("OpenCode execution failed: unavailable", category="unavailable")
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
