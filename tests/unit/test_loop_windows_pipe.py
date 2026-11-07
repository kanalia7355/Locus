"""Actual Windows kernel pipe tests use public synthetic packets, never keys."""

import sys
import threading
import time
from typing import Any
from uuid import uuid4

import pytest

from loop_engine.security import SafetyError
from loop_engine.windows_pipe import Native, pipe_name, request, serve_once, sid


@pytest.mark.parametrize("value", ["Locus-merge-v1", "Locus-review-v1"])
def test_fixed_local_endpoint_names(value: str) -> None:
    assert pipe_name(value).startswith("\\\\.\\pipe\\Locus-")


@pytest.mark.parametrize("value", ["\\\\remote\\pipe\\Locus-merge-v1", "../pipe", "arbitrary"])
def test_remote_and_arbitrary_endpoints_are_rejected(value: str) -> None:
    with pytest.raises(SafetyError):
        pipe_name(value)


@pytest.mark.parametrize("value", ["S-1-1-0", "S-1-5-32-545", "S-1-5-18", "S-1-5-19"])
def test_broad_and_shared_system_principals_are_rejected(value: str) -> None:
    with pytest.raises(SafetyError):
        sid(value)


WINDOWS = pytest.mark.skipif(
    sys.platform != "win32", reason="Actual Win32 named-pipe kernel required"
)


class Server:
    def __init__(self, handler: Any = None) -> None:
        self.name = "Locus-test-" + uuid4().hex
        self.identity = Native().current_sid()
        self.errors: list[BaseException] = []
        self.calls = 0
        self.cancelled = threading.Event()
        self.handler = handler
        self.thread = threading.Thread(target=self.run)

    def run(self) -> None:
        def handle(peer: str, data: dict[str, Any]) -> dict[str, Any]:
            self.calls += 1
            assert peer == self.identity
            return self.handler(data) if self.handler else {"value": data["value"]}

        try:
            serve_once(
                self.name, {self.identity}, handle, timeout=5, cancelled=self.cancelled.is_set
            )
        except BaseException as error:
            self.errors.append(error)

    def __enter__(self) -> "Server":
        self.thread.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self.cancelled.set()
        self.thread.join(6)
        assert not self.thread.is_alive()


@WINDOWS
def test_actual_kernel_owner_acl_peer_and_roundtrip() -> None:
    with Server() as server:
        reply = request(
            server.name, server.identity, {server.identity}, {"value": "synthetic"}, timeout=3
        )
        assert reply == {"value": "synthetic"}
        server.thread.join(2)
        assert server.calls == 1 and not server.errors


@WINDOWS
def test_wrong_kernel_owner_is_rejected_before_request_dispatch() -> None:
    with Server() as server:
        with pytest.raises(SafetyError, match="owner"):
            request(
                server.name,
                "S-1-5-21-11-22-33-4444",
                {server.identity},
                {"value": "synthetic"},
                timeout=3,
            )
        assert server.calls == 0


@WINDOWS
def test_unexpected_acl_inventory_is_rejected_before_dispatch() -> None:
    with Server() as server:
        with pytest.raises(SafetyError, match="principals"):
            request(
                server.name,
                server.identity,
                {server.identity, "S-1-5-21-11-22-33-4444"},
                {"value": "synthetic"},
                timeout=3,
            )
        assert server.calls == 0


@WINDOWS
def test_slow_reply_observes_absolute_client_deadline() -> None:
    def slow(data: dict[str, Any]) -> dict[str, Any]:
        time.sleep(0.8)
        return {"value": "synthetic"}

    with Server(slow) as server:
        started = time.monotonic()
        with pytest.raises(SafetyError, match="timed out"):
            request(
                server.name, server.identity, {server.identity}, {"value": "synthetic"}, timeout=0.2
            )
        assert time.monotonic() - started < 2


@WINDOWS
def test_cancelled_request_never_dispatches() -> None:
    with Server() as server:
        with pytest.raises(SafetyError, match="cancelled"):
            request(
                server.name,
                server.identity,
                {server.identity},
                {"value": "synthetic"},
                timeout=3,
                cancelled=lambda: True,
            )
        assert server.calls == 0
