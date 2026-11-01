"""Single-use, rejecting-by-default inference relay for the sealed audit client.

No request/header/input/response logging. Credentials exist only in memory. The
upstream is fixed HTTPS with default TLS verification, no proxy or redirects.
The supervisor owns the relay for one bounded invocation, never a public server.
"""

import http.client
import json
import socket
import ssl
import sys
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from loop_engine.security import SafetyError

HOST = "chatgpt.com"
PATH = "/backend-api/codex/responses"
INPUT_LIMIT = 4 * 1024 * 1024
OUTPUT_LIMIT = 16 * 1024 * 1024


def validate_inference(raw: bytes, model: str) -> dict[str, Any]:
    if not 0 < len(raw) <= INPUT_LIMIT:
        raise SafetyError("Audit inference request limit exceeded")

    def unique(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise SafetyError("Duplicate inference field")
            result[key] = value
        return result

    try:
        value = json.loads(raw, object_pairs_hook=unique)
        if (
            not isinstance(value, dict)
            or value.get("model") != model
            or value.get("tools", []) != []
            or "previous_response_id" in value
            or value.get("store") is not False
            or "input" not in value
        ):
            raise SafetyError("Audit inference capability/freshness differs")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise SafetyError("Audit inference rejected before forwarding") from None
    return value


class AuditRelay:
    def __init__(
        self,
        model: str,
        *,
        deadline: float,
        cancelled: Callable[[], bool],
        forwarding: bool = False,
        peer_authorized: Callable[[socket.socket], bool] = lambda _: False,
    ) -> None:
        self.model, self.deadline, self.cancelled = model, deadline, cancelled
        self.forwarding = forwarding
        self.observed = threading.Event()
        self.accepted = False
        self.used = False
        self.connection: http.client.HTTPSConnection | None = None
        relay = self

        class Server(HTTPServer):
            allow_reuse_address = False

            def server_bind(self) -> None:
                if sys.platform == "win32":
                    self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                super().server_bind()

            def get_request(self) -> tuple[socket.socket, Any]:
                client, address = super().get_request()
                try:
                    client.settimeout(min(5, relay.remaining()))
                    if not peer_authorized(client):
                        raise SafetyError("Audit relay client not authenticated")
                    return client, address
                except Exception:
                    client.close()
                    raise OSError("Audit relay client rejected") from None

            def handle_error(self, request: Any, client_address: Any) -> None:
                pass  # Never print exception, request, header or traceback.

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_: Any) -> None:
                pass

            def do_GET(self) -> None:
                self.send_response(405)
                self.end_headers()

            def do_POST(self) -> None:
                try:
                    length = self.headers.get_all("Content-Length", [])
                    if (
                        self.path != "/responses"
                        or len(length) != 1
                        or not length[0].isdigit()
                        or not 0 < int(length[0]) <= INPUT_LIMIT
                        or "Transfer-Encoding" in self.headers
                        or "Content-Encoding" in self.headers
                        or relay.used
                    ):
                        raise SafetyError("Invalid or repeated audit transport request")
                    relay.stage = "local_request"
                    relay.used = True
                    raw = self.rfile.read(int(length[0]))
                    if len(raw) != int(length[0]):
                        raise SafetyError("Truncated inference request")
                    validate_inference(raw, relay.model)
                    relay.accepted = True
                    relay.observed.set()
                    if not relay.forwarding:
                        self.send_response(400)
                        self.end_headers()
                        return
                    auth = self.headers.get_all("Authorization", [])
                    account = self.headers.get_all("ChatGPT-Account-ID", [])
                    if (
                        len(auth) != 1
                        or not auth[0].startswith("Bearer ")
                        or not 8 < len(auth[0]) <= 16384
                        or len(account) > 1
                        or (account and len(account[0]) > 256)
                    ):
                        raise SafetyError("Audit authentication header unavailable")
                    headers = {
                        "Authorization": auth[0],
                        "Content-Type": "application/json",
                        "Accept": "text/event-stream",
                        "User-Agent": "locus-audit-relay/1",
                    }
                    for name in (
                        "User-Agent",
                        "Originator",
                        "OpenAI-Beta",
                        "Session_id",
                        "X-Client-Request-Id",
                        "X-Codex-Turn-Metadata",
                        "X-Codex-Turn-State",
                    ):
                        values = self.headers.get_all(name, [])
                        if len(values) > 1 or (
                            values
                            and (
                                len(values[0]) > 4096
                                or any(not 32 <= ord(char) < 127 for char in values[0])
                            )
                        ):
                            raise SafetyError("Invalid fixed audit client metadata header")
                        if values:
                            headers[name] = values[0]
                    if account:
                        headers["ChatGPT-Account-ID"] = account[0]
                    relay.remaining()
                    connection = http.client.HTTPSConnection(
                        HOST,
                        timeout=min(10, relay.remaining()),
                        context=ssl.create_default_context(),
                    )
                    relay.connection = connection
                    relay.stage = "upstream_connect"
                    connection.request("POST", PATH, body=raw, headers=headers)
                    relay.stage = "upstream_headers"
                    response = connection.getresponse()
                    relay.http_status = response.status
                    relay.stage = "upstream_response"
                    if response.status != 200:
                        raise SafetyError(
                            "Audit upstream did not return success; no redirect/retry"
                        )
                    content_type = response.getheader("Content-Type", "")
                    if not content_type.startswith("text/event-stream"):
                        raise SafetyError("Audit upstream response format rejected")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    total = 0
                    relay.stage = "upstream_stream"
                    while True:
                        relay.remaining()
                        block = response.read1(8192)
                        if not block:
                            break
                        total += len(block)
                        if total > OUTPUT_LIMIT:
                            raise SafetyError("Audit inference response exceeded limit")
                        self.wfile.write(block)
                        self.wfile.flush()
                    relay.stage = "complete"
                except Exception as error:
                    relay.failure_reason = (
                        "timeout"
                        if isinstance(error, TimeoutError)
                        else "tls"
                        if isinstance(error, ssl.SSLError)
                        else "network"
                        if isinstance(error, OSError)
                        else "policy"
                    )
                    # Caller sees only a closed/failed bounded request, not input
                    # or response content. The nonce stays reserved on uncertainty.
                    self.close_connection = True
                finally:
                    if relay.connection:
                        relay.connection.close()
                        relay.connection = None

        self.server = Server(("127.0.0.1", 0), Handler)
        self.stage = "waiting_client"
        self.http_status: int | None = None
        self.failure_reason = "client_or_output_rejected"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def remaining(self) -> float:
        left = self.deadline - time.monotonic()
        if self.cancelled() or not 0 < left <= 300:
            raise SafetyError("Audit relay deadline expired or cancelled")
        return left

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    def __enter__(self) -> "AuditRelay":
        try:
            self.remaining()
            self.thread.start()
            return self
        except BaseException:
            self.server.server_close()
            raise

    def __exit__(self, *_: Any) -> None:
        if self.connection:
            self.connection.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(15)
        if self.thread.is_alive():
            raise SafetyError("Audit relay teardown uncertain; hold invocation")
