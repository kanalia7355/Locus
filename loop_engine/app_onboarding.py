"""One-time, operator-driven App registration; no signer/merge activation.

Temporary manifest codes and PEM material exist only in memory. The HTTP
handler suppresses request logging, never echoes query strings, and accepts
only an exact loopback Host, path and unpredictable session state.
"""

import html
import io
import json
import re
import secrets
import socket
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Protocol, cast
from urllib.parse import parse_qs, urlsplit

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from loop_engine.security import SafetyError

PERMISSIONS = {
    "review": {"contents": "read", "checks": "write", "pull_requests": "write"},
    "merge": {"contents": "write", "pull_requests": "write"},
}


class Vault(Protocol):
    def put(self, role: str, app_id: int, value: bytes) -> None: ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


class _DeadlineReader(io.BufferedIOBase):
    """Absolute session deadline and total header cap, even for trickled bytes."""

    def __init__(self, connection: socket.socket, deadline: float) -> None:
        self.connection, self.deadline = connection, deadline
        self.remaining = 16_384

    def readable(self) -> bool:
        return True

    def readline(self, size: int | None = -1) -> bytes:
        line = bytearray()
        limit = -1 if size is None else size
        while limit < 0 or len(line) < limit:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0 or self.remaining <= 0:
                raise TimeoutError("Registration request deadline/header limit")
            self.connection.settimeout(min(3, remaining))
            value = self.connection.recv(1)
            if not value:
                break
            self.remaining -= 1
            line.extend(value)
            if value == b"\n":
                break
        return bytes(line)


def convert_manifest(code: str) -> dict[str, Any]:
    if not re.fullmatch(r"[a-zA-Z0-9]{20,128}", code):
        raise SafetyError("Invalid manifest code")
    request = urllib.request.Request(  # noqa: S310 — fixed HTTPS host, validated path
        f"https://api.github.com/app-manifests/{code}/conversions",
        data=b"{}",
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Locus-App-Setup",
        },
    )
    # Ignore ambient proxy settings; neither credential responses nor one-time
    # codes may be redirected to a configured proxy/alternate endpoint.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=20) as response:
            if response.status != 201:
                raise SafetyError("App conversion did not complete")
            raw = response.read(64_001)
    except (OSError, urllib.error.URLError):
        raise SafetyError("App conversion failed; inspect registered Apps before retry") from None
    if len(raw) > 64_000:
        raise SafetyError("App conversion response too large")
    try:
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError
        return result
    except (ValueError, UnicodeError):
        raise SafetyError("Invalid App conversion response") from None


class Registration:
    def __init__(
        self,
        role: str,
        owner: str,
        vault: Vault,
        exchange: Callable[[str], dict[str, Any]] = convert_manifest,
    ) -> None:
        if role not in PERMISSIONS or not re.fullmatch(r"[A-Za-z0-9-]{1,39}", owner):
            raise SafetyError("Invalid App registration scope")
        self.role, self.owner, self.vault, self.exchange = role, owner, vault, exchange
        self.state = secrets.token_urlsafe(32)
        self.used = False

    def manifest(self, origin: str) -> dict[str, Any]:
        return {
            "name": f"Locus {self.role} {self.state[:8]}",
            "url": f"https://github.com/{self.owner}/Locus",
            "redirect_url": origin + "/callback",
            "hook_attributes": {"url": origin + "/disabled-hook", "active": False},
            "public": False,
            "default_permissions": PERMISSIONS[self.role],
            "default_events": [],
        }

    def accept(self, query: str) -> dict[str, Any]:
        values = parse_qs(query, strict_parsing=True, max_num_fields=2)
        if (
            self.used
            or set(values) != {"state", "code"}
            or any(len(value) != 1 for value in values.values())
            or not secrets.compare_digest(values["state"][0], self.state)
            or not re.fullmatch(r"[a-zA-Z0-9]{20,128}", values["code"][0])
        ):
            raise SafetyError("Registration callback rejected")
        self.used = True  # An uncertain conversion is never automatically replayed.
        result = self.exchange(values["code"][0])
        app_id, pem, slug = result.get("id"), result.get("pem"), result.get("slug")
        if (
            type(app_id) is not int
            or app_id <= 0
            or not isinstance(pem, str)
            or not isinstance(slug, str)
            or not re.fullmatch(r"[a-z0-9-]+", slug)
            or not isinstance(result.get("owner"), dict)
            or result["owner"].get("login") != self.owner
            or result.get("permissions") != {**PERMISSIONS[self.role], "metadata": "read"}
        ):
            raise SafetyError("App identity or permission response rejected")
        try:
            encoded = pem.encode("ascii")
            key = serialization.load_pem_private_key(encoded, password=None)
            if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < 2048:
                raise ValueError("Unsupported App key")
        except (ValueError, TypeError, UnicodeError, UnsupportedAlgorithm):
            raise SafetyError("App key validation failed") from None
        self.vault.put(self.role, app_id, encoded)
        # Only public identifiers leave the registration boundary.
        return {
            "role": self.role,
            "app_id": app_id,
            "slug": slug,
            "installation_url": f"https://github.com/apps/{slug}/installations/new",
            "activated": False,
        }


def register(role: str, owner: str, vault: Vault, timeout: int = 600) -> dict[str, Any]:
    """Serve one bounded interactive session. User creates/installs the App."""
    session = Registration(role, owner, vault)
    outcome: dict[str, Any] = {}
    deadline = time.monotonic() + min(max(timeout, 1), 600)

    class Handler(BaseHTTPRequestHandler):
        def setup(self) -> None:
            self.request.settimeout(3)
            super().setup()
            self.rfile.close()
            self.rfile = _DeadlineReader(self.connection, deadline)

        def log_message(self, format: str, *args: Any) -> None:
            pass

        def do_GET(self) -> None:
            origin = f"http://127.0.0.1:{cast(HTTPServer, self.server).server_port}"
            parsed = urlsplit(self.path)
            body, status = "Request rejected", 400
            if (
                len(self.path) <= 2048
                and self.headers.get("Host") == origin[7:]
                and not parsed.scheme
                and not parsed.netloc
            ):
                if parsed.path == "/" + session.state and not parsed.query:
                    manifest = html.escape(json.dumps(session.manifest(origin)), quote=True)
                    body = (
                        "<!doctype html><meta charset=utf-8><title>Locus App setup</title>"
                        "<p>Create the dedicated App, then install on Locus only. "
                        "This does not activate merging.</p>"
                        f'<form method="post" action="https://github.com/settings/apps/new?'
                        f'state={session.state}"><input type="hidden" name="manifest" '
                        f'value="{manifest}"><button>Create {role} App</button></form>'
                    )
                    status = 200
                elif parsed.path == "/callback":
                    try:
                        outcome.update(session.accept(parsed.query))
                        body = "Key saved in Windows Credential Manager. Return to the CLI."
                        status = 200
                    except (ValueError, OSError, RuntimeError, UnicodeError):
                        body = "Setup stopped. Inspect GitHub Apps before starting another session."
                        outcome["failed"] = True
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; form-action https://github.com; base-uri 'none'",
            )
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        server.timeout = 1
        print(f"Open locally: http://127.0.0.1:{server.server_port}/{session.state}", flush=True)
        while not outcome and time.monotonic() < deadline:
            server.handle_request()
    if not outcome or outcome.get("failed"):
        raise SafetyError("Registration incomplete; inspect GitHub Apps before retry")
    return outcome
