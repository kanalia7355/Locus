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
from loop_engine.security import SafetyError, create_text, fingerprint, within


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

    def __init__(self, root: Path, image_id: str, mcp_names: list[str]) -> None:
        self.root = root.resolve()
        self.native = NativeBoundary(root, mcp_names)
        self.docker = DockerBoundary(root, image_id)
        self.proof: dict[str, Any] | None = None
        home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
        catalog = (home / "models_cache.json").read_text(encoding="utf-8")
        self.catalog = within(root, ".loop/runtime/catalogs/" + fingerprint(catalog) + ".json")
        create_text(self.catalog, catalog)
        if self.catalog.read_text(encoding="utf-8") != catalog:
            raise SafetyError("Pinned model catalog changed")

    def _command(self, argv: list[str], workspace: Path) -> list[str]:
        self.docker.require(workspace, self.root)
        if argv[0] != codex_binary(self.root):
            raise SafetyError("Unexpected model client")
        if "exec" not in argv:
            if argv[1:] not in (["--version"], ["login", "status"]):
                raise SafetyError("Unknown preflight")
            return argv
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
            + [
                "--disable",
                "shell_tool",
                "--disable",
                "enable_request_compression",
                "--strict-config",
                "-c",
                "model_catalog_json=" + json.dumps(str(self.catalog)),
            ]
        )

    def _binding(self, workspace: Path) -> str:
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
        binding = self._binding(workspace)
        captured = threading.Event()
        observation: dict[str, Any] = {}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_: Any) -> None:
                pass

            def do_GET(self) -> None:
                self.send_response(503)
                self.end_headers()

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 5_000_000:
                    self.send_error(413)
                    return
                try:
                    body = json.loads(self.rfile.read(length))
                    if (
                        self.path.rstrip("/").endswith("/responses")
                        and isinstance(body, dict)
                        and "input" in body
                        and "model" in body
                    ):
                        tools = body.get("tools", [])
                        observation.update(
                            {
                                "no_tools": tools == [],
                                "fresh_request": "previous_response_id" not in body,
                            }
                        )
                        captured.set()
                except (ValueError, TypeError):
                    pass
                self.send_response(400)
                self.end_headers()

        with HTTPServer(("127.0.0.1", 0), Handler) as server:
            threading.Thread(target=server.serve_forever, daemon=True).start()
            binary = codex_binary(self.root)
            argv = self._command(
                [str(binary), "exec", "--json", "--ephemeral", "--cd", str(workspace), "-"],
                workspace,
            )
            argv += ["-c", f'openai_base_url="http://127.0.0.1:{server.server_port}"']
            outcome = ProcessRunner().run(
                argv,
                workspace,
                timeout=min(timeout, 35),
                stdin="Capability inspection only. No tools or external inference.",
                cancelled=lambda: captured.is_set() or cancelled(),
                model=True,
            )
            server.shutdown()
        self.proof = {
            "passed": captured.is_set()
            and observation.get("no_tools") is True
            and observation.get("fresh_request") is True
            and binding == self._binding(workspace),
            "binding": binding,
            "transport": "local rejecting inference endpoint",
            "client_outcome": outcome.outcome,
            "diagnostic": sanitized(outcome.stderr, 1500) if not captured.is_set() else "",
            **observation,
        }
        return self.proof
