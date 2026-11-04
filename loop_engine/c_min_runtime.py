"""Adapter for existing runner/relay, not an executor or authentication client."""

import ctypes
import json
import time
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from loop_engine.approval import ApprovalQueue
from loop_engine.audit_auth_state import key_metadata
from loop_engine.audit_transport import AuditRelay
from loop_engine.model_gate import validate_request
from loop_engine.model_invocations import InvocationJournal
from loop_engine.process import ProcessResult, ProcessRunner
from loop_engine.security import SafetyError, fingerprint, reparse, within
from loop_engine.state_store import StateStore
from loop_engine.windows_pipe import Native
from loop_engine.windows_tcp_peer import OwnedCliPeer


def file_security(path: Path) -> tuple[str, int, list[tuple[str, int, int]]]:
    original = path.absolute()
    if any(reparse(part) for part in (original, *original.parents)):
        raise SafetyError("Profile/log reparse boundary rejected")
    native = Native()
    handle = native.kernel.CreateFileW(str(original), 0x20000, 3, None, 3, 0x2200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise SafetyError("Profile/log security unavailable")
    try:
        return native.security(handle, kind=1)  # SE_FILE_OBJECT for this file/directory handle
    finally:
        native.kernel.CloseHandle(handle)


def privacy_options(root: Path) -> list[str]:
    """One private, write-denied log/SQLite sink; never change the auth home."""
    private_directory(root, ".loop/runtime/c_min")
    sink = within(root, ".loop/runtime/c_min/blocked-logs")
    sink.parent.mkdir(parents=True, exist_ok=True)
    owner = Native().current_sid()
    try:
        sink.mkdir()
    except FileExistsError:
        pass
    else:
        result = ProcessRunner().run(
            [
                "icacls.exe",
                str(sink),
                "/inheritance:r",
                "/grant:r",
                "*" + owner + ":(RX)",
                "*S-1-5-18:(F)",
                "*S-1-5-32-544:(F)",
            ],
            root,
            timeout=10,
        )
        if result.outcome != "exit" or result.returncode != 0:
            raise SafetyError("Private CLI log sink unavailable")
    identity, control, entries = file_security(sink)
    expected = {(owner, 0x1200A9, 0), ("S-1-5-18", 0x1F01FF, 0), ("S-1-5-32-544", 0x1F01FF, 0)}
    if (
        identity != owner
        or not control & 0x1000
        or set(entries) != expected
        or len(entries) != 3
        or any(sink.iterdir())
    ):
        raise SafetyError("CLI log/SQLite sink policy differs")
    cache = private_directory(root, ".loop/runtime/c_min/sqlite-state")
    return [
        "-c",
        "log_dir=" + json.dumps(str(sink)),
        "-c",
        "sqlite_home=" + json.dumps(str(cache)),
        "-c",
        "hide_agent_reasoning=true",
        "-c",
        "show_raw_agent_reasoning=false",
    ]


def private_directory(root: Path, relative: str) -> Path:
    if relative.startswith(".loop/runtime/c_min/"):
        private_directory(root, ".loop/runtime/c_min")
    cache = within(root, relative)
    cache.parent.mkdir(parents=True, exist_ok=True)
    owner = Native().current_sid()
    try:
        cache.mkdir()
    except FileExistsError:
        pass
    else:
        result = ProcessRunner().run(
            [
                "icacls.exe",
                str(cache),
                "/inheritance:r",
                "/grant:r",
                "*" + owner + ":(OI)(CI)(M)",
                "*S-1-5-18:(OI)(CI)(F)",
                "*S-1-5-32-544:(OI)(CI)(F)",
            ],
            root,
            timeout=10,
        )
        if result.outcome != "exit" or result.returncode != 0:
            raise SafetyError("Private ephemeral CLI metadata directory unavailable")
    identity, control, entries = file_security(cache)
    expected_cache = {
        (owner, 0x1301BF, 3),
        ("S-1-5-18", 0x1F01FF, 3),
        ("S-1-5-32-544", 0x1F01FF, 3),
    }
    if (
        identity != owner
        or not control & 0x1000
        or len(entries) != 3
        or set(entries) != expected_cache
    ):
        raise SafetyError("Private CLI metadata directory policy differs")
    return cache


def verify_profile(state: StateStore) -> None:
    """Only headers/existence of the already registered storage; no secret blobs."""
    import os

    profile = state.metadata("c_min_auth_profile")
    common = {"home", "backend", "config_hash", "sid", "protection"}
    file_backed = isinstance(profile, dict) and profile.get("backend") == "existing-file"
    expected = common | (
        {"file_identity"}
        if file_backed
        else {
            "home",
            "backend",
            "config_hash",
            "key_metadata",
            "ciphertext_identity",
            "sid",
            "protection",
        }
    )
    if not isinstance(profile, dict) or set(profile) != expected:
        raise SafetyError("Nonsecret operator auth profile requires reconciliation")
    original_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).absolute()
    if any(reparse(part) for part in (original_home, *original_home.parents)):
        raise SafetyError("Original operator profile traverses reparse boundary")
    home = original_home.resolve()
    # The pinned CLI loads this before processing its config. Never read its
    # values: they can reintroduce provider/proxy/auth environment overrides.
    if (home / ".env").exists() or reparse(home / ".env"):
        raise SafetyError("Unassessed client dotenv file; no authentication loaded")
    if reparse(home) or not (home / "config.toml").is_file() or reparse(home / "config.toml"):
        raise SafetyError("Nonsecret profile path differs")
    raw = (home / "config.toml").read_text(encoding="utf-8")
    settings = tomllib.loads(raw)
    if file_backed:
        from loop_engine.auth_file_profile import inspect_existing

        if (
            profile["home"] != str(home)
            or profile["sid"] != Native().current_sid()
            or fingerprint(raw) != profile["config_hash"]
            or settings.get("cli_auth_credentials_store") not in {None, "file"}
            or settings.get("features", {}).get("secret_auth_storage", False) is not False
            or (home / "secrets/codex_auth.age").exists()
        ):
            raise SafetyError("Registered existing-file profile differs")
        actual = inspect_existing(home, profile["sid"])
        if actual != {
            "file_identity": profile["file_identity"],
            "protection": profile["protection"],
        }:
            raise SafetyError("Existing auth file changed; no repair/retry")
        return
    encrypted = profile["backend"] == "encrypted-keyring"
    if (
        profile["home"] != str(home)
        or profile["sid"] != Native().current_sid()
        or profile["backend"] not in {"keyring", "encrypted-keyring"}
        or fingerprint(raw) != profile["config_hash"]
        or settings.get("cli_auth_credentials_store") != "keyring"
        or bool(settings.get("features", {}).get("secret_auth_storage", False)) != encrypted
        or (home / "auth.json").exists()
    ):
        raise SafetyError("Existing auth storage binding differs")
    stamp = key_metadata(home, direct=not encrypted)
    if stamp is None or stamp != profile["key_metadata"]:
        raise SafetyError("Existing auth key missing/changed; preserve state")
    identity = None
    protected_paths = {"home": home, "config": home / "config.toml"}
    if encrypted:
        folder = home / "secrets"
        path = folder / "codex_auth.age"
        if (
            reparse(folder)
            or reparse(path)
            or not path.is_file()
            or set(x.name for x in folder.iterdir()) != {path.name}
        ):
            raise SafetyError("Existing ciphertext lifecycle uncertain")
        with path.open("rb") as stream:
            if not stream.read(24).startswith(b"age-encryption.org/v1\n"):
                raise SafetyError("Existing ciphertext envelope differs")
        stat = path.stat()
        identity = [stat.st_ino, stat.st_size, stat.st_mtime_ns]
        protected_paths.update(secrets=folder, ciphertext=path)
    if identity != profile["ciphertext_identity"]:
        raise SafetyError("Existing auth artifact changed; preserve state")
    protection = {}
    for label, path in protected_paths.items():
        security = file_security(path)
        if security[0] != profile["sid"]:
            raise SafetyError("Existing profile artifact owner differs")
        protection[label] = fingerprint(security)
    if protection != profile["protection"]:
        raise SafetyError("Existing auth access conditions changed; preserve state")


def preflight(root: Path, state: StateStore, artifact: str) -> None:
    """Nonsecret authorization only. Never load auth to find out whether it exists."""
    from loop_engine.runtime_diagnostics import runtime_identity

    permit = state.metadata("c_min_live_permit")
    if (
        not isinstance(permit, dict)
        or set(permit) != {"operation", "runtime", "artifact", "run", "expires"}
        or permit["operation"] != "c-min-normal-development"
        or permit["runtime"] != runtime_identity(root)
        or permit["artifact"] != artifact
        or permit["run"] != state.metadata("run_budget", {}).get("id")
        or type(permit["expires"]) not in {float, int}
        or not time.time()
        < permit["expires"]
        <= state.metadata("run_budget", {}).get("deadline", 0)
        or ApprovalQueue(state).status(None, "scope", fingerprint(permit)) != "approved"
    ):
        raise SafetyError("Separate exact C-min live/run authorization is absent")
    verify_profile(state)
    from loop_engine.runtime_diagnostics import require_receipt

    require_receipt(root)


def invoke(
    root: Path,
    state: StateStore,
    boundary: Any,
    process: ProcessRunner,
    argv: list[str],
    prompt: str,
    workspace: Path,
    schema: dict[str, Any],
    owner: dict[str, Any],
    deadline: float,
    cancelled: Callable[[], bool],
    *,
    trial_approval: str | None = None,
) -> tuple[ProcessResult, InvocationJournal, str]:
    artifact = boundary._binding(workspace)
    trial = None
    if trial_approval is None:
        preflight(root, state, artifact)
    else:
        from loop_engine.c_min_trial import PROMPT, SCHEMA, authorize
        from loop_engine.c_min_trial import reserve as reserve_trial

        trial = authorize(root, state, workspace, artifact, trial_approval)
        if prompt != PROMPT or schema != SCHEMA:
            raise SafetyError("Fixed synthetic trial contract required")
        boundary.docker.require(workspace, root)
        if not boundary.docker.audit_evidence(root):
            raise SafetyError("Current source QA image audit required before trial")
        verify_profile(state)
        deadline = min(deadline, time.monotonic() + max(0, trial["expires"] - time.time()))
        owner = reserve_trial(state, trial, artifact)
    journal = InvocationJournal(state)
    expires = time.time() + max(0, deadline - time.monotonic())
    if trial is not None:
        expires = min(expires, trial["expires"])
    identifier = journal.claim(owner, artifact, expires)
    peer = OwnedCliPeer(argv[0])
    temp_relative = ".loop/runtime/c_min/invocations/" + identifier + "/temp"
    temporary = private_directory(root, temp_relative)
    versioned = trial is not None and "input_version" in trial
    arg0 = None
    packet: dict[str, Any] = {}
    anchors: dict[str, Any] = {}

    def bind_child(pid: int, job: Any) -> None:
        private_directory(root, temp_relative)
        peer.bind(pid, job)
        if versioned:
            anchors.update(utc=time.time(), monotonic=time.monotonic())

    def remaining() -> float:
        left = deadline - time.monotonic()
        if cancelled() or left <= 0:
            raise SafetyError("C-min invocation expired")
        return min(left, 300)

    def request(raw: bytes) -> Any:
        remaining()
        result = validate_request(raw, "gpt-6.1-sol", schema, {str(root), str(workspace)})
        if versioned:
            packet["raw"] = raw
        elif trial is not None:
            from loop_engine.c_min_trial import exact_input

            exact_input(result, trial)
        if not versioned:
            journal.advance(identifier, "launch_reserved", "request_validated")
        return result

    def binding() -> dict[str, Any]:
        from loop_engine.trial_input_binding import validate

        remaining()
        assert trial is not None and arg0 is not None
        identity = peer.identity()
        profile = state.metadata("c_min_auth_profile")
        if identity["sid"] != profile["sid"]:
            raise SafetyError("Trial issuing operator changed")
        context = {
            **anchors,
            **identity,
            "active": True,
            "now": time.time(),
            "monotonic_now": time.monotonic(),
            "expires": expires,
            "not_before": trial["expires"] - 180,
            "launch": {
                "runtime": trial["runtime"],
                "artifact": artifact,
                "workspace": str(workspace.resolve()),
                "profile": trial["profile"],
                "history": trial["history"],
                "model": "gpt-6.1-sol",
                "destination": "https://chatgpt.com/backend-api/codex/responses",
                "argv": argv,
                "schema": fingerprint(schema),
            },
        }
        return validate(
            state.metadata("c_min_trial_input_contract"),
            packet["raw"],
            packet["headers"],
            context,
            arg0.check,
        )

    def headers(values: dict[str, str]) -> None:
        packet["headers"] = values
        packet["binding"] = binding()
        journal.bind_trial_input(identifier, packet["binding"])

    def reserve() -> None:
        remaining()
        if artifact != boundary._binding(workspace):
            raise SafetyError("C-min launch binding changed")
        if versioned:
            from loop_engine.c_min_trial import authorize

            assert trial is not None and trial_approval is not None
            if authorize(root, state, workspace, artifact, trial_approval) != trial:
                raise SafetyError("Trial approval changed before send")
            verify_profile(state)
            if not boundary.docker.audit_evidence(root):
                raise SafetyError("Trial QA audit changed before send")
            if packet["binding"] != binding():
                raise SafetyError("Trial request identity changed before send")
            if journal.trial_binding(identifier, "request_validated") != packet["binding"]:
                raise SafetyError("Durable trial input binding changed")
        journal.advance(identifier, "request_validated", "upstream_reserved")
        if arg0 is not None:
            arg0.close()

    try:
        if versioned:
            from loop_engine.trial_arg0 import Arg0Guard

            profile = state.metadata("c_min_auth_profile")
            arg0 = Arg0Guard(Path(profile["home"]), profile["sid"], remaining)
        with AuditRelay(
            "gpt-6.1-sol",
            deadline=time.monotonic() + remaining(),
            cancelled=cancelled,
            peer_authorized=peer,
            forwarding=True,
            request_validator=request,
            reserve_upstream=reserve,
            trial_headers=headers if versioned else None,
            trial_input_version=trial["input_version"] if versioned and trial is not None else None,
        ) as relay:
            command = (
                boundary.command(argv, workspace)
                if trial is None
                else boundary._command(argv, workspace)
            ) + [
                "-c",
                'model_provider="openai"',
                "-c",
                "openai_base_url=" + json.dumps(relay.url),
            ]
            journal.advance(identifier, "prepared", "launch_reserved")
            outcome = process.run(
                command,
                workspace,
                timeout=remaining(),
                stdin=prompt,
                model=True,
                before_resume=bind_child,
                private_temp=temporary,
                cancelled=lambda: cancelled() or relay.failed,
            )
            if (
                outcome.outcome != "exit"
                or outcome.returncode != 0
                or relay.failed
                or not relay.response_gate
                or not relay.response_gate.completed
                or relay.stage != "complete"
                or artifact != boundary._binding(workspace)
            ):
                raise SafetyError("C-min transport did not complete cleanly")
            journal.advance(identifier, "upstream_reserved", "terminal_validated")
            verify_profile(state)
            privacy_options(root)
            if trial is not None:
                from loop_engine.runtime_diagnostics import runtime_identity

                if runtime_identity(root) != trial["runtime"] or not boundary.docker.audit_evidence(
                    root
                ):
                    raise SafetyError("Trial runtime/source QA changed before final proof")
            if any(temporary.iterdir()):
                raise SafetyError("Unexpected model temporary artifact; preserve and hold")
        return outcome, journal, identifier
    except BaseException:
        journal.hold(identifier)
        raise
    finally:
        if arg0 is not None:
            arg0.close()
        peer.close()
