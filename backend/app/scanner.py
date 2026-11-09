"""Opt-in, bounded loopback ClamAV transport. No connection during construction.

Every scan returns a typed, fail-closed outcome instead of a bare boolean so a
check that could not run (timeout, connection error, busy adapter, unusable
reply) is never reported as an explicit rejection verdict. All non-clean
outcomes keep ingestion quarantined; only the interpretation differs.
"""

import os
import socket
import struct
import threading
import time
from dataclasses import dataclass
from typing import Literal

Outcome = Literal["clean", "rejected", "unavailable"]


@dataclass(frozen=True)
class ScanResult:
    """Typed scanner verdict: clean / rejected / unavailable-or-error."""

    outcome: Outcome


CLEAN = ScanResult("clean")
REJECTED = ScanResult("rejected")
UNAVAILABLE = ScanResult("unavailable")

OK_REPLY = b"stream: OK\0"


class ClamAVScanner:
    def __init__(self) -> None:
        self._lock = threading.Lock()

    def scan(self, content: str) -> ScanResult:
        if not isinstance(content, str) or not content:
            # The adapter refuses input it cannot scan at all: a content-level
            # rejection, not an operational failure of the check.
            return REJECTED
        try:
            payload = content.encode("utf-8")
        except UnicodeError:
            return REJECTED
        if len(payload) > 262144:
            # The bounded transport refuses content it could never scan: a
            # content-level rejection, not an operational failure.
            return REJECTED
        if not self._lock.acquire(blocking=False):
            # A busy adapter means the check could not run; that is not a
            # verdict about the content.
            return UNAVAILABLE
        try:
            deadline = time.monotonic() + 10.0
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:

                def remaining() -> None:
                    seconds = deadline - time.monotonic()
                    if seconds <= 0:
                        raise TimeoutError
                    connection.settimeout(seconds)

                remaining()
                connection.connect(("127.0.0.1", 3310))
                remaining()
                connection.sendall(b"zINSTREAM\0")
                remaining()
                connection.sendall(struct.pack("!I", len(payload)) + payload)
                remaining()
                connection.sendall(b"\0\0\0\0")
                response = bytearray()
                while True:
                    remaining()
                    part = connection.recv(1025 - len(response))
                    remaining()
                    if not part:
                        reply = bytes(response)
                        if reply == OK_REPLY:
                            return CLEAN
                        if reply.endswith(b"\0"):
                            # A complete daemon verdict that is not clean is an
                            # explicit rejection.
                            return REJECTED
                        # The reply was cut off before a complete verdict, so
                        # the outcome is unknown rather than rejected.
                        return UNAVAILABLE
                    response.extend(part)
                    if len(response) > 1024:
                        # Protocol anomaly: the reply cannot be trusted, so the
                        # check counts as unavailable instead of a verdict.
                        return UNAVAILABLE
        except Exception:
            # Timeout / connection / I/O errors: the check could not complete.
            return UNAVAILABLE
        finally:
            self._lock.release()


def scanner_from_environment() -> ClamAVScanner | None:
    setting = os.environ.get("LOCUS_SCANNER", "")
    if setting in {"", "disabled"}:
        return None
    if setting == "clamav":
        return ClamAVScanner()
    raise ValueError("Unknown LOCUS_SCANNER setting")
