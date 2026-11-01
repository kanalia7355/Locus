"""Fixed credential profile and real synthetic capability probe, before enrolment.

The new account gets its own encryption-key keyring entry and private ciphertext
directory. The remaining home and logging directories deny writes, except two
precreated nonsecret lock/installation files.
No operator auth cache is copied or used. Only synthetic credentials are probed.
"""

import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from loop_engine.audit_auth_state import AuthState
from loop_engine.audit_identity import AuditDeployment
from loop_engine.audit_packet import canonical, decode
from loop_engine.audit_transport import AuditRelay
from loop_engine.native_boundary import DISABLED
from loop_engine.process import ProcessRunner
from loop_engine.security import SafetyError
from loop_engine.service_identity import protected_bytes
from loop_engine.windows_tcp_peer import require_loopback_peer

FEATURES = (
    *DISABLED,
    "shell_tool",
    "enable_request_compression",
    "responses_websockets",
    "responses_websockets_v2",
)


def profile_text(runtime: Path, model: str, reasoning_effort: str | None = None) -> str:
    lines = [
        'cli_auth_credentials_store="keyring"',
        "model=" + json.dumps(model),
        *(["model_reasoning_effort=" + json.dumps(reasoning_effort)] if reasoning_effort else []),
        "model_catalog_json=" + json.dumps(str(runtime / "models.json")),
        "log_dir=" + json.dumps(str(runtime / "blocked-logs")),
        "skills.bundled.enabled=false",
        "skills.include_instructions=false",
        "analytics.enabled=false",
        "feedback.enabled=false",
        'otel.exporter="none"',
        'otel.trace_exporter="none"',
        'otel.metrics_exporter="none"',
        "otel.log_user_prompt=false",
        "otel.log_agent_responses=false",
        "otel.log_guardian_assessments=false",
        "hide_agent_reasoning=true",
        "show_raw_agent_reasoning=false",
        "mcp_servers={}",
        "[history]",
        'persistence="none"',
        "[features]",
        "secret_auth_storage=true",
        *(feature + "=false" for feature in FEATURES),
    ]
    return "\n".join(lines) + "\n"


def relay_overrides(url: str) -> list[str]:
    import re

    match = re.fullmatch(r"http://127\.0\.0\.1:([0-9]{1,5})", url)
    if match is None or not 0 < int(match[1]) <= 65535:
        raise SafetyError("Fixed local audit relay origin required")
    # CLI0.166.0 ignores overrides to the built-in provider record. A private
    # transport alias retains OpenAI/ChatGPT auth but forces HTTP to our relay.
    # The relay, not this alias, owns the one fixed external HTTPS destination.
    return [
        "-c",
        'model_provider="locus_audit_openai"',
        "-c",
        'model_providers.locus_audit_openai.name="OpenAI"',
        "-c",
        "model_providers.locus_audit_openai.base_url=" + json.dumps(url),
        "-c",
        'model_providers.locus_audit_openai.wire_api="responses"',
        "-c",
        "model_providers.locus_audit_openai.requires_openai_auth=true",
        "-c",
        "model_providers.locus_audit_openai.supports_websockets=false",
        "-c",
        "model_providers.locus_audit_openai.request_max_retries=0",
        "-c",
        "model_providers.locus_audit_openai.stream_max_retries=0",
    ]


def auth_command(binary: Path, *arguments: str) -> list[str]:
    # CLI0.166.0 explicitly rejects --strict-config for login/logout. Fixed
    # read-only profile and the approved encrypted backend enforce storage.
    return [
        str(binary),
        "-c",
        'cli_auth_credentials_store="keyring"',
        "--enable",
        "secret_auth_storage",
        *arguments,
    ]


def check_profile(deployment: AuditDeployment, home: Path) -> None:
    deployment.require_role("audit")
    if home not in {deployment.state / "home", deployment.state / "probe-home"}:
        raise SafetyError("Fixed account-local audit profile required")
    if os.environ.get("CODEX_HOME") != str(home):
        raise SafetyError("Audit profile environment changed")
    workspace = deployment.state / "empty"
    if not workspace.is_dir() or any(workspace.iterdir()):
        raise SafetyError("Empty sealed audit workspace required")
    for directory in (workspace, *workspace.parents):
        for relative in ("AGENTS.md", ".codex/config.toml", ".codex/hooks.json", ".agents/skills"):
            if (directory / relative).exists():
                raise SafetyError("Unassessed audit launch instructions/hooks; no bypass")
    # A machine-wide policy must be assessed, never overridden to make the probe
    # pass. The dedicated home intentionally inherits no operator configuration.
    machine = Path("C:/ProgramData/OpenAI/Codex")
    if machine.exists() and any(machine.iterdir()):
        raise SafetyError("Machine Codex policy requires assessment before enrolment")
    expected = profile_text(
        getattr(deployment, "profile_runtime", deployment.runtime),
        deployment.settings["model"],
        deployment.settings["reasoning_effort"],
    ).encode()
    if protected_bytes(home / "config.toml") != expected:
        raise SafetyError("Audit authentication/model policy changed")
    if {item.name for item in home.iterdir()} != {
        "config.toml",
        "auth.lock",
        "installation_id",
        "secrets",
    }:
        raise SafetyError("Unexpected cache/auth file in read-only audit home")
    import ctypes

    from loop_engine.audit_identity import require_private_acl
    from loop_engine.windows_pipe import Native

    native = Native()
    secrets_directory = home / "secrets"
    from loop_engine.security import reparse

    if reparse(secrets_directory) or not secrets_directory.is_dir():
        raise SafetyError("Private encrypted credential directory required")
    handle = native.kernel.CreateFileW(str(secrets_directory), 0x20000, 3, None, 3, 0x2200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise SafetyError("Encrypted credential directory ACL unavailable")
    try:
        require_private_acl(*native.security(handle), deployment.settings["audit_sid"])
    finally:
        native.kernel.CloseHandle(handle)
    if (home / "auth.lock").stat().st_size != 0:
        raise SafetyError("Unexpected credential-lock contents")
    identifier = (home / "installation_id").read_text(encoding="ascii")
    if str(UUID(identifier)) != identifier:
        raise SafetyError("Invalid audit installation metadata")
    logs = getattr(deployment, "profile_runtime", deployment.runtime) / "blocked-logs"
    if not logs.is_dir() or any(logs.iterdir()):
        raise SafetyError("Audit logging is not disabled by filesystem policy")
    for directory in (home, logs):
        try:
            with (directory / ("denial-probe-" + uuid4().hex)).open("xb"):
                pass
        except PermissionError:
            continue
        raise SafetyError("Audit profile/log directory unexpectedly writable")


def preflight(
    deployment: AuditDeployment,
    *,
    deadline: float,
    cancelled: Callable[[], bool],
    process: ProcessRunner | None = None,
) -> dict[str, Any]:
    process = process or ProcessRunner()

    def remaining() -> float:
        left = deadline - time.monotonic()
        if cancelled() or not 0 < left <= 300:
            raise SafetyError("Audit preflight expired/cancelled")
        return left

    remaining()
    deployment.require_role("audit")
    deployment.require_private_state()
    real_home, home = deployment.state / "home", deployment.state / "probe-home"
    if os.environ.get("CODEX_HOME") != str(real_home):
        raise SafetyError("Unexpected audit enrolment profile")
    check_profile(deployment, real_home)
    AuthState(real_home).check()
    journal = deployment.state / "keyring-probe.json"
    if journal.exists():
        previous = decode(journal.read_bytes(), 4096)
        if previous != {
            "identity": getattr(deployment, "state_identity", deployment.identity),
            "phase": "complete",
        }:
            raise SafetyError("Uncertain synthetic credential probe; reconcile without replay")
        if AuthState(home).check() != "probe_cleared":
            raise SafetyError("Completed synthetic authentication lifecycle changed")
        AuthState(real_home).check()
        return {
            "role": "audit",
            "keyring_verified": True,
            "zero_tools_verified": True,
            "plaintext_cache_absent": True,
            "log_writes_denied": True,
            "activated": False,
        }
    # This account-local record contains only fixed metadata, never credentials.
    from loop_engine.security import atomic_text

    atomic_text(journal, canonical({"identity": deployment.identity, "phase": "started"}).decode())
    binary = deployment.runtime / "codex.exe"
    os.environ["CODEX_HOME"] = str(home)  # Only this owned worker, never host/operator environment.
    saved = False
    authentication = AuthState(home)
    try:
        check_profile(deployment, home)
        authentication.begin("probe")
        result = process.run(
            auth_command(binary, "login", "--with-api-key"),
            deployment.state,
            # Probe an OAuth-sized record rather than only a short API key.
            stdin="synthetic-audit-probe-not-a-real-credential-" + "x" * 6144,
            timeout=min(30, remaining()),
            cancelled=cancelled,
            model=True,
            output_limit=8192,
            active_process_limit=1,
        )
        saved = result.outcome == "exit" and result.returncode == 0
        if not saved:
            raise SafetyError("Dedicated keyring storage unavailable; no file fallback")
        authentication.finish("probe_ready")
        authentication.begin("use")
        status = process.run(
            auth_command(binary, "login", "status"),
            deployment.state,
            timeout=min(15, remaining()),
            cancelled=cancelled,
            model=True,
            output_limit=8192,
            active_process_limit=1,
        )
        if status.outcome != "exit" or status.returncode != 0:
            raise SafetyError("Fresh-process keyring persistence not established")
        authentication.finish("probe_ready")
        check_profile(deployment, home)
        with AuditRelay(
            deployment.settings["model"],
            deadline=time.monotonic() + min(35, remaining()),
            cancelled=cancelled,
            peer_authorized=lambda connection: require_loopback_peer(
                connection, deployment.settings["audit_sid"]
            ),
        ) as relay:
            argv = [
                str(binary),
                "exec",
                "--json",
                "--ephemeral",
                "--strict-config",
                "--skip-git-repo-check",
                "--cd",
                str(deployment.state / "empty"),
                "-c",
                'approval_policy="never"',
                "-c",
                'web_search="disabled"',
                "-c",
                'cli_auth_credentials_store="keyring"',
                "-c",
                'shell_environment_policy.inherit="none"',
            ]
            argv += relay_overrides(relay.url)
            for feature in FEATURES:
                argv.extend(["--disable", feature])
            argv.extend(["--enable", "secret_auth_storage"])
            authentication.begin("use")
            process.run(
                argv + ["-"],
                deployment.state / "empty",
                stdin="Synthetic zero-tool capability probe; no inference.",
                timeout=min(35, remaining()),
                cancelled=lambda: cancelled() or relay.observed.is_set(),
                model=True,
                output_limit=8192,
                active_process_limit=1,
            )
            if not relay.accepted:
                raise SafetyError("Actual audit zero-tool inference request not established")
            authentication.finish("probe_ready")
        remaining()
        check_profile(deployment, home)
    finally:
        if saved:
            # Bounded cleanup of our known synthetic record even if cancelled.
            # No real account session has ever been stored in this probe profile.
            authentication.begin("probe_clear")
            cleared = process.run(
                auth_command(binary, "logout"),
                deployment.state,
                timeout=10,
                model=True,
                output_limit=8192,
                active_process_limit=1,
            )
            if cleared.outcome != "exit" or cleared.returncode != 0:
                os.environ["CODEX_HOME"] = str(real_home)
                raise SafetyError("Synthetic credential cleanup uncertain; hold enrolment")
            authentication.finish("probe_cleared")
        os.environ["CODEX_HOME"] = str(real_home)
    remaining()
    check_profile(deployment, real_home)
    atomic_text(journal, canonical({"identity": deployment.identity, "phase": "complete"}).decode())
    return {
        "role": "audit",
        "keyring_verified": True,
        "zero_tools_verified": True,
        "plaintext_cache_absent": True,
        "log_writes_denied": True,
        "activated": False,
    }
