"""Opt-in, bounded loopback ClamAV transport. No connection during construction."""

import os
import socket
import struct
import threading
import time


class ClamAVScanner:
    def __init__(self) -> None:
        self._lock = threading.Lock()

    def scan(self, content: str) -> bool:
        if not isinstance(content, str) or not content:
            return False
        try:
            payload = content.encode("utf-8")
        except UnicodeError:
            return False
        if len(payload) > 262144 or not self._lock.acquire(blocking=False):
            return False
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
                        return bytes(response) == b"stream: OK\0"
                    response.extend(part)
                    if len(response) > 1024:
                        return False
        except Exception:
            return False
        finally:
            self._lock.release()


def scanner_from_environment() -> ClamAVScanner | None:
    setting = os.environ.get("LOCUS_SCANNER", "")
    if setting in {"", "disabled"}:
        return None
    if setting == "clamav":
        return ClamAVScanner()
    raise ValueError("Unknown LOCUS_SCANNER setting")
