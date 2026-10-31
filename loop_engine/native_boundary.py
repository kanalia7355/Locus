"""Native Codex tool permissions with concrete source/control/network probes."""

import json
import re
import socket
import sys
import tempfile
from pathlib import Path
from typing import Any

from loop_engine.codex_runner import codex_binary
from loop_engine.process import ProcessRunner
from loop_engine.security import SafetyError, reparse

DISABLED = (
    "multi_agent",
    "apps",
    "plugins",
    "remote_plugin",
    "browser_use",
    "browser_use_external",
    "browser_use_full_cdp_access",
    "in_app_browser",
    "computer_use",
    "image_generation",
    "code_mode_host",
    "skill_mcp_dependency_install",
    "workspace_dependencies",
    "shell_snapshot",
    "memories",
)


class NativeBoundary:
    def __init__(self, root: Path, mcp_names: list[str]) -> None:
        self.root = root.resolve()
        self.binary = codex_binary(root)
        if any(not re.fullmatch(r"[A-Za-z0-9_-]+", name) for name in mcp_names):
            raise SafetyError("Unsupported MCP identifier; cannot guarantee tool disablement")
        self.mcp_names = mcp_names
        self.proof: dict[str, Any] | None = None

    def settings(self, workspace: Path, readonly: bool) -> list[str]:
        rules = {
            ":root": "deny",
            ":minimal": "read",
            str(workspace.resolve()).replace("\\", "/"): "read" if readonly else "write",
        }
        for runtime in (Path(sys.base_prefix), Path(sys.executable).parent.parent):
            rules[str(runtime.resolve()).replace("\\", "/")] = "read"
        for path in (
            self.root / ".git",
            self.root / ".loop/runtime",
            Path.home() / ".codex",
            Path.home() / ".config/gh",
            Path.home() / ".ssh",
            Path.home() / ".aws",
        ):
            if not workspace.resolve().is_relative_to(path.resolve()):
                rules[str(path.resolve()).replace("\\", "/")] = "deny"
        for name in (
            ".git",
            ".codex",
            ".loop",
            ".env",
            "storage",
            "uploads",
            "auth.json",
            "credentials.json",
        ):
            rules[str((workspace / name).resolve()).replace("\\", "/")] = "deny"
        table = (
            "{"
            + ",".join(json.dumps(key) + "=" + json.dumps(value) for key, value in rules.items())
            + "}"
        )
        result = [
            "-c",
            'windows.sandbox="mxc"',
            "-c",
            'default_permissions="locus-loop"',
            "-c",
            'permissions.locus-loop.extends=":workspace"',
            "-c",
            "permissions.locus-loop.filesystem=" + table,
            "-c",
            "permissions.locus-loop.network.enabled=false",
            "-c",
            'approval_policy="never"',
            "-c",
            'web_search="disabled"',
        ]
        for feature in DISABLED:
            result += ["--disable", feature]
        for name in self.mcp_names:
            result += ["-c", "mcp_servers." + name + ".enabled=false"]
        return result

    def require(self, workspace: Path, control_root: Path) -> None:
        if (
            control_root.resolve() != self.root
            or not self.binary
            or not self.proof
            or self.proof.get("passed") is not True
        ):
            raise SafetyError("Native tool capabilities not proven")
        if reparse(workspace) or not workspace.is_dir():
            raise SafetyError("Unsafe source workspace")

    def command(self, argv: list[str], workspace: Path) -> list[str]:
        self.require(workspace, self.root)
        if argv[0] != self.binary:
            raise SafetyError(
                "Native boundary accepts only the pinned Codex executable; QA uses Docker"
            )
        if "exec" not in argv:
            if argv[1:] not in (["--version"], ["login", "status"]):
                raise SafetyError("Unsupported Codex preflight")
            return argv
        readonly = "read-only" in argv
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
        return result + self.settings(workspace, readonly)

    def probe(self) -> dict[str, Any]:
        if not self.binary:
            raise SafetyError("Native Codex unavailable")
        runtime = self.root / ".loop/runtime/probes"
        runtime.mkdir(parents=True, exist_ok=True)
        name = tempfile.mkdtemp(prefix="native-", dir=runtime)
        directory = Path(name).resolve()
        if not directory.is_relative_to(runtime.resolve()):
            raise SafetyError("Probe escaped runtime")
        workspace = directory / "source"
        workspace.mkdir()
        control = directory / "synthetic-control"
        control.write_text("synthetic only", encoding="utf-8")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            port = listener.getsockname()[1]
            code = f"""from pathlib import Path
import socket
print("STARTED")
Path("output.txt").write_text("synthetic")
print("SOURCE_WRITE")
try:
    Path({str(control)!r}).read_text()
    print("CONTROL_LEAK")
except PermissionError:
    print("CONTROL_DENIED")
try:
    Path(".codex").mkdir()
    print("POLICY_WRITE")
except PermissionError:
    print("POLICY_DENIED")
try:
    socket.create_connection(("127.0.0.1",{port}),timeout=2).close()
    print("NETWORK_ALLOWED")
except OSError:
    print("NETWORK_DENIED")
"""
            script = workspace / "probe.py"
            script.write_text(code, encoding="utf-8")
            import sys

            outcome = ProcessRunner().run(
                [
                    self.binary,
                    "sandbox",
                    "-P",
                    "locus-loop",
                    *self.settings(workspace, False),
                    "-C",
                    str(workspace),
                    "--",
                    sys.executable,
                    str(script),
                ],
                workspace,
                timeout=30,
            )
            markers = set(outcome.stdout.splitlines())
            passed = (
                outcome.returncode == 0
                and {"STARTED", "SOURCE_WRITE", "CONTROL_DENIED", "POLICY_DENIED", "NETWORK_DENIED"}
                <= markers
                and not {"CONTROL_LEAK", "POLICY_WRITE", "NETWORK_ALLOWED"} & markers
            )
            from loop_engine.checks import sanitized

            self.proof = {
                "passed": passed,
                "markers": sorted(markers),
                "exit_code": outcome.returncode,
                "diagnostic": sanitized(outcome.stderr, 3000),
            }
            return self.proof
