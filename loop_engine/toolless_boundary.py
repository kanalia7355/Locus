"""Text-only Codex proposals: verify the actual inference request advertises no tools."""

import hashlib
import json
import os
import threading
import tomllib
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from loop_engine.checks import sanitized
from loop_engine.codex_runner import codex_binary
from loop_engine.docker_boundary import DockerBoundary
from loop_engine.native_boundary import NativeBoundary
from loop_engine.process import ProcessRunner
from loop_engine.security import SafetyError, create_text, fingerprint, reparse, within


def tool_surface(body: Any) -> dict[str, Any]:
    """Inspect standard and Lite declarations; retain no input/header values."""
    fields = {
        "model",
        "input",
        "instructions",
        "tools",
        "tool_choice",
        "parallel_tool_calls",
        "reasoning",
        "text",
        "stream",
        "store",
        "include",
        "max_output_tokens",
        "service_tier",
        "prompt_cache_key",
        "prompt_cache_retention",
        "metadata",
        "client_metadata",
        "temperature",
        "top_p",
        "truncation",
        "safety_identifier",
    }
    valid = (
        isinstance(body, dict)
        and isinstance(body.get("model"), str)
        and bool(body["model"].strip())
        and set(body) <= fields
    )
    fresh = valid and not any(key in body for key in ("previous_response_id", "conversation"))
    count = 0

    def inspect(value: Any) -> None:
        nonlocal valid, fresh, count
        if isinstance(value, dict):
            if "tools" in value:
                if not isinstance(value["tools"], list):
                    valid = False
                else:
                    count += len(value["tools"])
            kind = value.get("type", "")
            if isinstance(kind, str) and (kind.endswith("_call") or kind.endswith("_call_output")):
                fresh = False
            if kind == "additional_tools" and not isinstance(value.get("tools"), list):
                valid = False
            for item in value.values():
                inspect(item)
        elif isinstance(value, list):
            for item in value:
                inspect(item)

    if valid:
        inputs = body.get("input")
        if not isinstance(inputs, (list, str)):
            valid = False
        elif isinstance(inputs, list):
            for item in inputs:
                if not isinstance(item, dict) or item.get("type", "message") not in {
                    "message",
                    "additional_tools",
                }:
                    valid = False
                elif item.get("type") == "additional_tools":
                    if set(item) != {"type", "tools"}:
                        valid = False
                else:
                    content = item.get("content")
                    if (
                        not set(item) <= {"type", "role", "content"}
                        or item.get("role") not in {"system", "developer", "user"}
                        or not isinstance(content, (str, list))
                    ):
                        valid = False
                    elif isinstance(content, list) and any(
                        not isinstance(part, dict)
                        or set(part) != {"type", "text"}
                        or part.get("type") != "input_text"
                        or not isinstance(part.get("text"), str)
                        for part in content
                    ):
                        valid = False
    # Unsupported metadata still cannot hide executable definitions from the
    # diagnostic count; unsupported shape remains a failed proof independently.
    if isinstance(body, dict):
        inspect(body)
    return {
        "surface_version": 2,
        "no_tools": bool(valid and count == 0),
        "fresh_request": bool(fresh and valid),
        "declared_tools": count,
        "request_shape_supported": bool(valid),
    }


def probe_json(raw: bytes) -> Any:
    """Duplicate keys and non-JSON numeric constants cannot prove absence."""

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate probe field")
            result[key] = value
        return result

    def constant(_: str) -> Any:
        raise ValueError("Invalid JSON constant")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def configured_hooks(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            (key == "hooks" and not isinstance(item, bool) and bool(item)) or configured_hooks(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(configured_hooks(item) for item in value)
    return False


class ToollessBoundary:
    file_proposals = True
    c_min = True

    def __init__(self, root: Path, image_id: str, mcp_names: list[str]) -> None:
        self.root = root.resolve()
        self.native = NativeBoundary(root, mcp_names)
        self.docker = DockerBoundary(root, image_id)
        self.proof: dict[str, Any] | None = None
        home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
        catalog = (home / "models_cache.json").read_text(encoding="utf-8")
        values = json.loads(catalog)
        selected = [item for item in values["models"] if item.get("slug") == "gpt-6.1-sol"]
        if len(selected) != 1 or selected[0].get("use_responses_lite") is not True:
            raise SafetyError("Pinned C-min Lite model missing")
        selected[0].update(
            tool_mode="direct",
            experimental_supported_tools=[],
            apply_patch_tool_type=None,
            shell_type="disabled",
            multi_agent_version=None,
        )
        catalog = json.dumps(values, sort_keys=True)
        self.catalog = within(root, ".loop/runtime/catalogs/" + fingerprint(catalog) + ".json")
        create_text(self.catalog, catalog)
        if self.catalog.read_text(encoding="utf-8") != catalog:
            raise SafetyError("Pinned model catalog changed")

    def _command(self, argv: list[str], workspace: Path) -> list[str]:
        self.docker.require(workspace, self.root)
        if argv[0] != codex_binary(self.root):
            raise SafetyError("Unexpected model client")
        if "exec" not in argv:
            if argv[1:] != ["--version"]:
                raise SafetyError("C-min authentication commands are not preflight")
            if argv[1:] not in (["--version"], ["login", "status"]):
                raise SafetyError("Unknown preflight")
            return argv
        from loop_engine.c_min_runtime import privacy_options

        privacy = privacy_options(self.root)
        result = []
        index = 0
        while index < len(argv):
            if argv[index] == "--sandbox":
                index += 2
                continue
            if argv[index] == "-c" and argv[index + 1].startswith("sandbox_workspace_write."):
                index += 2
                continue
            result.append(argv[index])
            index += 1
        return (
            result
            + self.native.settings(workspace, True)
            + privacy
            + [
                "--disable",
                "shell_tool",
                "--disable",
                "enable_request_compression",
                "--strict-config",
                "-c",
                "model_catalog_json=" + json.dumps(str(self.catalog)),
                "-c",
                'model="gpt-6.1-sol"',
                "-c",
                "features.multi_agent_v2={enabled=false,disable_native_tools=true}",
                "-c",
                "tools.experimental_request_user_input.enabled=false",
                "-c",
                "tools.update_plan.enabled=false",
                "-c",
                'history.persistence="none"',
                "-c",
                "analytics.enabled=false",
                "-c",
                "feedback.enabled=false",
                "-c",
                'otel.exporter="none"',
                "-c",
                'otel.trace_exporter="none"',
                "-c",
                'otel.metrics_exporter="none"',
                "-c",
                "otel.log_user_prompt=false",
                "-c",
                "otel.log_agent_responses=false",
                *[
                    value
                    for feature in (
                        "view_image",
                        "sleep_tool",
                        "current_time_reminder",
                        "token_budget",
                        "deferred_executor",
                        "request_permissions_tool",
                        "send_message_to_user_async",
                        "code_mode",
                        "code_mode_only",
                        "multi_agent_v2_dynamic_tools",
                    )
                    for value in ("--disable", feature)
                ],
            ]
        )

    def _binding(self, workspace: Path) -> str:
        machine = Path("C:/ProgramData/OpenAI/Codex")
        if machine.exists() and any(machine.iterdir()):
            raise SafetyError("Machine model policy requires separate assessment; no bypass")
        binary = codex_binary(self.root)
        if binary is None:
            raise SafetyError("Missing model client")
        configuration: dict[str, str] = {}
        home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
        candidates = [
            home / "config.toml",
            home / "AGENTS.md",
            self.catalog,
            home / "hooks.json",
            home / "requirements.toml",
        ]
        for directory in [workspace.resolve(), *workspace.resolve().parents]:
            candidates.extend([directory / "AGENTS.md", directory / ".codex/config.toml"])
            candidates.append(directory / ".codex/hooks.json")
            for relative in (".agents/skills", ".codex/skills"):
                folder = directory / relative
                if folder.is_dir():
                    candidates.extend(folder.rglob("SKILL.md"))
        for path in sorted(set(candidates)):
            if path.is_file():
                if path.name == "config.toml" and configured_hooks(
                    tomllib.loads(path.read_text(encoding="utf-8"))
                ):
                    raise SafetyError(
                        "Installed lifecycle hooks require assessment; hooks are not bypassed"
                    )
                if path.name == "hooks.json" and json.loads(
                    path.read_text(encoding="utf-8")
                ) not in ({}, {"hooks": {}}):
                    raise SafetyError(
                        "Installed lifecycle hooks require assessment; hooks are not bypassed"
                    )
                configuration[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        return fingerprint(
            {
                "binary": hashlib.sha256(Path(binary).read_bytes()).hexdigest(),
                "workspace": str(workspace.resolve()),
                "settings": self.native.settings(workspace, True),
                "mode": "text-only",
                "configuration": configuration,
            }
        )

    def require(self, workspace: Path, control_root: Path) -> None:
        self.docker.require(workspace, control_root)
        from loop_engine.runtime_diagnostics import require_receipt

        require_receipt(self.root)
        if self.c_min:
            if control_root.resolve() != self.root or reparse(workspace) or not workspace.is_dir():
                raise SafetyError("Unsafe C-min workspace")
            self._binding(workspace)  # Includes mandatory hook/skill assessment.
            return
        if (
            not self.proof
            or self.proof.get("passed") is not True
            or self.proof.get("binding") != self._binding(workspace)
        ):
            raise SafetyError("No verified zero-tool inference surface for this workspace")

    def command(self, argv: list[str], workspace: Path) -> list[str]:
        self.require(workspace, self.root)
        return self._command(argv, workspace)

    def probe(
        self,
        workspace: Path,
        *,
        timeout: float = 35,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> dict[str, Any]:
        """Local rejecting endpoint: inspect tool definitions without model inference.

        Headers and request input are neither inspected nor logged. No request
        is forwarded. Only the tool count and request shape become evidence.
        """
        # An ordinary home may load/refresh credentials even for a rejecting mock.
        # Offline C-min conformance runs use explicitly isolated test profiles;
        # never call the legacy credential-bearing probe as an implicit preflight.
        if self.c_min:
            return {
                "passed": False,
                "surface_version": 3,
                "diagnostic_only": True,
                "no_tools": False,
                "fresh_request": False,
                "reason": "isolated_offline_proof_and_separate_live_permission_required",
            }
        binding = self._binding(workspace)
        captured = threading.Event()
        observation: dict[str, Any] = {}

        class Handler(BaseHTTPRequestHandler):
            def setup(self) -> None:
                super().setup()
                self.connection.settimeout(min(2, max(0.1, timeout)))

            def log_message(self, *_: Any) -> None:
                pass

            def do_GET(self) -> None:
                self.send_response(503)
                self.end_headers()

            def do_POST(self) -> None:
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except (ValueError, TypeError):
                    self.send_error(400)
                    return
                if not 0 < length <= 5_000_000:
                    self.send_error(413)
                    return
                try:
                    body = probe_json(self.rfile.read(length))
                    if (
                        self.path.rstrip("/").endswith("/responses")
                        and isinstance(body, dict)
                        and "input" in body
                        and "model" in body
                    ):
                        observation.update(tool_surface(body))
                        captured.set()
                except (ValueError, TypeError, OSError, RecursionError):
                    pass
                try:
                    self.send_response(400)
                    self.end_headers()
                except OSError:
                    pass

        with HTTPServer(("127.0.0.1", 0), Handler) as server:
            binary = codex_binary(self.root)
            argv = self._command(
                [str(binary), "exec", "--json", "--ephemeral", "--cd", str(workspace), "-"],
                workspace,
            )
            from loop_engine.audit_profile import relay_overrides

            # Reuse the existing fixed-loopback transport alias: CLI0.166.0
            # ignores the former built-in openai_base_url override. This endpoint
            # rejects requests, never forwards inference and never logs auth.
            argv += relay_overrides(f"http://127.0.0.1:{server.server_port}")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                outcome = ProcessRunner().run(
                    argv,
                    workspace,
                    timeout=min(timeout, 35),
                    stdin="Capability inspection only. No tools or external inference.",
                    cancelled=lambda: captured.is_set() or cancelled(),
                    model=True,
                )
            finally:
                server.shutdown()
                thread.join(2)
        self.proof = {
            # The fixed local alias safely diagnoses actual Lite declarations,
            # but it is not proof that a different provider identifier advertises
            # an identical surface. Never promote that unresolved equivalence
            # into permission to run the normal provider.
            "passed": False,
            "diagnostic_only": True,
            "native_provider_equivalence_verified": False,
            "binding_unchanged": binding == self._binding(workspace),
            "binding": binding,
            "transport": "local rejecting inference endpoint",
            "client_outcome": outcome.outcome,
            "diagnostic": sanitized(outcome.stderr, 1500) if not captured.is_set() else "",
            **observation,
        }
        return self.proof
