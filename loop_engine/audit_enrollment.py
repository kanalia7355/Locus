"""Owner-only private UI bridge, owned by the long-lived audit SCM host.

Never called by Controller/model tools. The owner CLI polls fixed status plus
the one-use link/code directly on their console, not via assistant tool output.
No key, token, arbitrary CLI output or diagnostics are returned or persisted.
"""

import re
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from loop_engine.audit_auth_state import AuthState
from loop_engine.audit_profile import auth_command
from loop_engine.process import ProcessRunner
from loop_engine.security import SafetyError

DEVICE_URL = "https://auth.openai.com/codex/device"
_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


class Enrollment:
    def __init__(
        self,
        binary: Path,
        workspace: Path,
        *,
        preflight: Callable[[], None],
        stopped: Callable[[], bool],
        process: ProcessRunner | None = None,
        authentication: AuthState | None = None,
    ) -> None:
        self.binary, self.workspace = binary, workspace
        self.preflight, self.stopped = preflight, stopped
        self.process = process or ProcessRunner()
        self.authentication = authentication
        self.lock = threading.Lock()
        self.abort = threading.Event()
        self.thread: threading.Thread | None = None
        self.deadline = 0.0
        self.last_poll = 0.0
        self.state = "idle"
        self.code: str | None = None
        self.failure_stage: str | None = None
        self.failure_reason: str | None = None
        self.http_status: int | None = None

    def start(self, deadline: float) -> dict[str, Any]:
        if not 0 < deadline - time.monotonic() <= 300 or self.stopped():
            raise SafetyError("Bounded active owner authentication required")
        with self.lock:
            if self.thread is not None:
                raise SafetyError("Existing authentication attempt requires status/reconciliation")
            self.deadline = deadline
            self.last_poll = time.monotonic()
            self.state = "preflight"
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()
        return {"status": "started", "authenticated": False, "activated": False}

    def poll(self) -> dict[str, Any]:
        with self.lock:
            self.last_poll = time.monotonic()
            answer: dict[str, Any] = {
                "status": self.state,
                "authenticated": self.state == "authenticated",
                "activated": False,
            }
            if self.state == "waiting_for_owner" and self.code is not None:
                answer.update(verification_uri=DEVICE_URL, user_code=self.code)
            if self.state == "held":
                answer.update(
                    stage=self.failure_stage,
                    reason=self.failure_reason,
                    http_status=self.http_status,
                )
            return answer

    def cancel(self) -> dict[str, Any]:
        self.abort.set()
        return {"status": "cancellation_requested", "activated": False}

    def _cancelled(self) -> bool:
        return (
            self.abort.is_set()
            or self.stopped()
            or time.monotonic() >= self.deadline
            or time.monotonic() - self.last_poll > 10
        )

    def _run(self) -> None:
        transient = bytearray()
        stage = "preflight"
        reason = "preflight_failed"

        def observe(channel: int, chunk: bytes) -> None:
            if channel != 0:
                return
            if len(transient) + len(chunk) > 8192:
                raise SafetyError("Authentication UI output exceeded bound")
            transient.extend(chunk)
            text = _ANSI.sub("", transient.decode("utf-8", errors="replace"))
            # Only the documented origin plus an exact bounded code is exposed.
            # No generic URL/text forwarding, stderr or auth transcript storage.
            match = re.search(r"(?m)^\s*([A-Z0-9]{4}-[A-Z0-9]{4,5})\s*$", text)
            if DEVICE_URL in text and match:
                with self.lock:
                    self.code = match[1]
                    self.state = "waiting_for_owner"

        try:
            if self.authentication is None:
                raise SafetyError("Protected authentication lifecycle required")
            self.preflight()
            if self._cancelled():
                raise SafetyError("Owner authentication cancelled before sign-in")
            stage, reason = "existing_authentication", "existing_login_unclassified"
            previous_phase = self.authentication.check()
            if previous_phase not in {"pristine", "enrolled"}:
                raise SafetyError("Real authentication profile lifecycle required")
            if previous_phase == "enrolled":
                self.authentication.begin("use")
            existing = self.process.run(
                auth_command(self.binary, "login", "status"),
                self.workspace,
                timeout=min(15, self.deadline - time.monotonic()),
                cancelled=self._cancelled,
                model=True,
                output_limit=8192,
                active_process_limit=1,
            )
            lines = existing.stderr.strip().splitlines()
            if existing.outcome != "exit" or not lines:
                raise SafetyError("Existing audit authentication is uncertain; preserve it")
            if existing.returncode == 0:
                if previous_phase != "enrolled":
                    raise SafetyError("Unexpected authentication in pristine profile")
                if lines[-1] != "Logged in using ChatGPT":
                    raise SafetyError("Unexpected existing authentication method; preserve it")
                self.authentication.finish("enrolled")
                with self.lock:
                    self.state = "authenticated"
                return
            if existing.returncode != 1 or lines[-1] != "Not logged in":
                raise SafetyError("Existing audit authentication cannot be classified; preserve it")
            if previous_phase != "pristine" or self.authentication.check() != "pristine":
                raise SafetyError("Existing login missing; preserve authentication lifecycle")
            with self.lock:
                self.state = "starting_login"
            stage, reason = "device_login", "device_login_failed"
            self.authentication.begin("enrol")
            outcome = self.process.run(
                auth_command(self.binary, "login", "--device-auth"),
                self.workspace,
                timeout=self.deadline - time.monotonic(),
                cancelled=self._cancelled,
                model=True,
                output_limit=8192,
                output_observer=observe,
                active_process_limit=1,
            )
            authenticated = (
                outcome.outcome == "exit" and outcome.returncode == 0 and not self._cancelled()
            )
            if not authenticated:
                if (
                    "not enabled" in outcome.stderr.lower()
                    or "not supported" in outcome.stderr.lower()
                ):
                    reason = "device_auth_not_enabled"
                status = re.search(r"\b(401|403|404|429|500|502|503)\b", outcome.stderr)
                if status:
                    self.http_status = int(status[1])
            if authenticated:
                self.authentication.finish("enrolled")
                self.authentication.begin("use")
                stage, reason = "verification", "login_verification_failed"
                check = self.process.run(
                    auth_command(self.binary, "login", "status"),
                    self.workspace,
                    timeout=min(15, self.deadline - time.monotonic()),
                    cancelled=self._cancelled,
                    model=True,
                    output_limit=8192,
                    active_process_limit=1,
                )
                authenticated = (
                    check.outcome == "exit"
                    and check.returncode == 0
                    and not self._cancelled()
                    and check.stderr.strip().splitlines()[-1:] == ["Logged in using ChatGPT"]
                )
                if authenticated:
                    self.authentication.finish("enrolled")
            with self.lock:
                self.state = "authenticated" if authenticated else "held"
                if not authenticated:
                    self.failure_stage, self.failure_reason = stage, reason
        except Exception:
            with self.lock:
                self.state = "held"
                self.failure_stage = stage
                self.failure_reason = "cancelled_or_expired" if self._cancelled() else reason
        finally:
            transient.clear()
            with self.lock:
                self.code = None
