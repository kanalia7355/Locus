import socket
import struct

import pytest
from app import scanner
from app.scanner import CLEAN, REJECTED, UNAVAILABLE


class Socket:
    def __init__(self, parts):
        self.parts = iter(parts)
        self.sent = []
        self.closed = False
        self.timeouts = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def settimeout(self, value):
        self.timeouts.append(value)

    def connect(self, target):
        assert target == ("127.0.0.1", 3310)

    def sendall(self, value):
        self.sent.append(value)

    def recv(self, maximum):
        part = next(self.parts)
        if isinstance(part, BaseException):
            raise part
        assert len(part) <= maximum
        return part


def install(monkeypatch, parts):
    connection = Socket(parts)
    calls = []

    def factory(*args):
        calls.append(args)
        return connection

    monkeypatch.setattr(scanner.socket, "socket", factory)
    return connection, calls


def test_framing_split_reply_and_cleanup(monkeypatch):
    connection, calls = install(monkeypatch, [b"stream:", b" OK\0", b""])
    adapter = scanner.ClamAVScanner()
    assert adapter.scan("合成") == CLEAN
    payload = "合成".encode()
    assert connection.sent == [b"zINSTREAM\0", struct.pack("!I", len(payload)) + payload, bytes(4)]
    assert calls == [(socket.AF_INET, socket.SOCK_STREAM)]
    assert connection.closed
    assert all(0 < value <= 10 for value in connection.timeouts)
    assert adapter._lock.acquire(False)
    adapter._lock.release()


@pytest.mark.parametrize(
    ["parts", "expected"],
    [
        # Explicit daemon verdict that is not the clean sentinel: a rejection.
        ([b"stream: FOUND\0", b""], REJECTED),
        # Complete-but-duplicated reply: a daemon verdict that is not clean.
        ([b"stream: OK\0stream: OK\0", b""], REJECTED),
        # Replies cut off or malformed before a trustworthy verdict: the check
        # could not complete, which is unavailable rather than a rejection.
        ([b"stream: OK", b""], UNAVAILABLE),
        ([b"stream: OK\0extra", b""], UNAVAILABLE),
        ([b""], UNAVAILABLE),
        ([b"x" * 1025], UNAVAILABLE),
        # Transport failures and timeouts: unavailable, never a verdict.
        ([TimeoutError()], UNAVAILABLE),
        ([OSError()], UNAVAILABLE),
        ([b"stream: OK\0", TimeoutError()], UNAVAILABLE),
    ],
)
def test_fail_closed_outcomes(monkeypatch, parts, expected):
    connection, _ = install(monkeypatch, parts)
    adapter = scanner.ClamAVScanner()
    assert adapter.scan("synthetic") == expected
    assert connection.closed
    assert adapter._lock.acquire(False)
    adapter._lock.release()


@pytest.mark.parametrize("content", ["", None, "\ud800", "a" * 262145, "あ" * 87382])
def test_invalid_input_rejected_without_io(monkeypatch, content):
    _, calls = install(monkeypatch, [])
    assert scanner.ClamAVScanner().scan(content) == REJECTED
    assert not calls


def test_busy_no_io(monkeypatch):
    _, calls = install(monkeypatch, [])
    adapter = scanner.ClamAVScanner()
    adapter._lock.acquire()
    try:
        # A busy adapter cannot run the check: unavailable, not a verdict.
        assert adapter.scan("synthetic") == UNAVAILABLE
        assert not calls
    finally:
        adapter._lock.release()


def test_total_deadline(monkeypatch):
    connection, _ = install(monkeypatch, [])
    times = iter([0, 1, 11])
    monkeypatch.setattr(scanner.time, "monotonic", lambda: next(times))
    assert scanner.ClamAVScanner().scan("synthetic") == UNAVAILABLE
    assert connection.sent == []
    assert connection.closed


def test_explicit_configuration_without_io(monkeypatch):
    _, calls = install(monkeypatch, [])
    monkeypatch.delenv("LOCUS_SCANNER", raising=False)
    assert scanner.scanner_from_environment() is None
    monkeypatch.setenv("LOCUS_SCANNER", "disabled")
    assert scanner.scanner_from_environment() is None
    monkeypatch.setenv("LOCUS_SCANNER", "clamav")
    assert isinstance(scanner.scanner_from_environment(), scanner.ClamAVScanner)
    monkeypatch.setenv("LOCUS_SCANNER", "other")
    with pytest.raises(ValueError):
        scanner.scanner_from_environment()
    assert not calls


def test_reply_cut_off_before_verdict_is_unavailable(monkeypatch):
    connection, _ = install(monkeypatch, [b"stream: OK\0", b""])
    times = iter([0, 1, 2, 3, 4, 5, 9, 9, 11])
    monkeypatch.setattr(scanner.time, "monotonic", lambda: next(times))
    assert scanner.ClamAVScanner().scan("synthetic") == UNAVAILABLE
    assert connection.closed


@pytest.mark.parametrize("operation", ["connect", "sendall", "recv"])
def test_cancellation_releases_resources(monkeypatch, operation):
    connection, _ = install(monkeypatch, [])

    def cancel(*args):
        raise KeyboardInterrupt

    monkeypatch.setattr(connection, operation, cancel)
    adapter = scanner.ClamAVScanner()
    with pytest.raises(KeyboardInterrupt):
        adapter.scan("synthetic")
    assert connection.closed
    assert adapter._lock.acquire(False)
    adapter._lock.release()
