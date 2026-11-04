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

from loop_engine.model_gate import ResponseGate, strict_json
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

        def invalid_constant(_value: str) -> None:
            raise ValueError("Nonstandard JSON constant")

        value = json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant)
        if (
            not isinstance(value, dict)
            or value.get("model") != model
            or value.get("tools", []) != []
            or "previous_response_id" in value
            or value.get("store") is not False
            or not isinstance(value.get("input"), list)
        ):
            raise SafetyError("Audit inference capability/freshness differs")
        # Responses Lite relocates tool definitions into additional_tools input
        # items. Checking only top-level tools incorrectly admits those tools.
        for item in value["input"]:
            if not isinstance(item, dict):
                raise SafetyError("Typed fresh inference input required")
            kind = item.get("type", "message")
            if not isinstance(kind, str) or kind.endswith(("_call", "_call_output")):
                raise SafetyError("Tool calls/history are not fresh read-only input")
            if kind == "additional_tools" and (
                item.get("role") != "developer" or item.get("tools") != []
            ):
                raise SafetyError("Embedded inference tools are not permitted")
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
        request_validator: Callable[[bytes], Any] | None = None,
        reserve_upstream: Callable[[], None] | None = None,
        trial_headers: Callable[[dict[str, str]], None] | None = None,
        trial_input_version: str | None = None,
    ) -> None:
        self.model, self.deadline, self.cancelled = model, deadline, cancelled
        self.forwarding = forwarding
        self.observed = threading.Event()
        self.accepted = False
        self.used = False
        self.failed = False
        self.upgrade_rejected = 0
        self.response_gate = ResponseGate(model) if request_validator else None
        self.connection: http.client.HTTPSConnection | None = None
        self.client_socket: socket.socket | None = None
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
                    relay.client_socket = client
                    return client, address
                except Exception:
                    if request_validator:
                        relay.failed = True
                    client.close()
                    raise OSError("Audit relay client rejected") from None

            def handle_error(self, request: Any, client_address: Any) -> None:
                pass  # Never print exception, request, header or traceback.

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1" if request_validator else "HTTP/1.0"

            def parse_request(self) -> bool:
                if not request_validator:
                    return super().parse_request()
                original = self.rfile

                class Budget:
                    total = 0

                    def readline(self, size: int = -1) -> bytes:
                        data = original.readline(min(size if size > 0 else 65537, 65537))
                        self.total += len(data)
                        if self.total > 65536:
                            raise http.client.LineTooLong("C-min bounded headers")
                        return data

                self.rfile = Budget()  # type: ignore[assignment]
                try:
                    return super().parse_request()
                finally:
                    self.rfile = original

            def send_error(
                self, code: int, message: str | None = None, explain: str | None = None
            ) -> None:
                if request_validator:
                    relay.failed = True
                    self.send_response(code)
                    self.end_headers()
                    self.close_connection = True
                else:
                    super().send_error(code, message, explain)

            def log_message(self, *_: Any) -> None:
                pass

            def do_GET(self) -> None:
                if request_validator:
                    if (
                        self.path == "/responses"
                        and self.headers.get("Upgrade", "").lower() == "websocket"
                        and self.headers.get("Connection", "").lower() == "upgrade"
                        and self.headers.get("Sec-WebSocket-Version") == "13"
                        and self.headers.get("Content-Length", "0") == "0"
                        and "Transfer-Encoding" not in self.headers
                        and not relay.used
                        and relay.upgrade_rejected < 1
                    ):
                        # Pinned official client treats 426 as immediate HTTP selection.
                        # No WebSocket is established and no bytes go to provider.
                        relay.upgrade_rejected += 1
                        self.send_response(426)
                        self.send_header("Content-Length", "0")
                        self.send_header("Connection", "close")
                        self.end_headers()
                        return
                    relay.failed = True
                self.send_response(405)
                self.end_headers()

            def do_POST(self) -> None:
                try:
                    if request_validator and (
                        len(self.headers) > 64 or len(bytes(self.headers)) > 65536
                    ):
                        raise SafetyError("C-min header bound exceeded")
                    if request_validator and (
                        self.headers.get_all("Content-Type", []) != ["application/json"]
                        or any(
                            len(values) != 1
                            for key in self.headers
                            if (values := self.headers.get_all(key, []))
                        )
                    ):
                        raise SafetyError("C-min duplicate/type headers rejected")
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
                    if request_validator:
                        parsed_request = request_validator(raw)
                    else:
                        validate_inference(raw, relay.model)
                    lite = self.headers.get_all("X-OpenAI-Internal-Codex-Responses-Lite", [])
                    if len(lite) > 1 or (lite and lite != ["true"]):
                        raise SafetyError("Invalid fixed Responses Lite protocol header")
                    if request_validator and lite != ["true"]:
                        raise SafetyError("C-min Lite marker required")
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
                        or (request_validator is not None and len(account) != 1)
                        or (
                            request_validator is not None
                            and any(
                                not value or any(not 32 <= ord(c) < 127 for c in value)
                                for value in [*auth, *account]
                            )
                        )
                    ):
                        raise SafetyError("Audit authentication header unavailable")
                    headers = {
                        "Authorization": auth[0],
                        "Content-Type": "application/json",
                        "Accept": "text/event-stream",
                        "User-Agent": "locus-audit-relay/1",
                    }
                    if lite:
                        headers["X-OpenAI-Internal-Codex-Responses-Lite"] = "true"
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
                            if request_validator:
                                if name == "X-Codex-Turn-State":
                                    raise SafetyError("C-min continuation header rejected")
                                if name == "OpenAI-Beta" and values != ["responses=experimental"]:
                                    raise SafetyError("C-min protocol extension header rejected")
                                if name == "X-Codex-Turn-Metadata":
                                    encoded = parsed_request.get("client_metadata", {}).get(
                                        "x-codex-turn-metadata"
                                    )
                                    if not isinstance(encoded, str) or strict_json(
                                        values[0].encode()
                                    ) != strict_json(encoded.encode()):
                                        raise SafetyError("C-min authoritative header differs")
                            headers[name] = values[0]
                    if account:
                        headers["ChatGPT-Account-ID"] = account[0]
                    if trial_headers is not None:
                        from loop_engine.trial_input_binding import VERSION, input_headers

                        allowed_headers = input_headers(trial_input_version or VERSION)

                        mechanical = {
                            "host",
                            "content-length",
                            "content-type",
                            "accept",
                            "accept-encoding",
                            "connection",
                        }
                        names = [name.lower() for name in self.headers.keys()]
                        if (
                            len(names) != len(set(names))
                            or set(names)
                            - allowed_headers
                            - mechanical
                            - {"authorization", "chatgpt-account-id"}
                            or self.headers.get("Host")
                            != f"127.0.0.1:{relay.server.server_address[1]}"
                        ):
                            raise SafetyError("Trial HTTP header inventory differs")
                        # Authentication is never passed to the binding hook, hashed or recorded.
                        trial_headers(
                            {name: self.headers[name] for name in names if name in allowed_headers}
                        )
                    relay.remaining()
                    if request_validator:
                        if reserve_upstream is None:
                            raise SafetyError("C-min durable reservation required")
                        reserve_upstream()
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
                    if content_type.split(";", 1)[0].strip().lower() != "text/event-stream":
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
                        for safe in (
                            relay.response_gate.feed(block) if relay.response_gate else [block]
                        ):
                            self.wfile.write(safe)
                            self.wfile.flush()
                    if relay.response_gate:
                        relay.response_gate.finish()
                    relay.stage = "complete"
                except Exception as error:
                    relay.failed = True
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
        self.thread = threading.Thread(
            target=lambda: self.server.serve_forever(poll_interval=0.05), daemon=True
        )

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
        if self.client_socket:
            try:
                self.client_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.client_socket.close()
        if self.connection:
            try:
                if self.connection.sock:
                    self.connection.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.connection.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(15)
        if self.thread.is_alive():
            raise SafetyError("Audit relay teardown uncertain; hold invocation")
