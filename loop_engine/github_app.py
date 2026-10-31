"""Short-lived repo-only installation credentials; fixed HTTPS origin, no CLI."""

import base64
import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from email.utils import parsedate_to_datetime
from typing import Any, Literal, Protocol

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from loop_engine.app_onboarding import PERMISSIONS, _NoRedirect
from loop_engine.security import SafetyError


class KeyReader(Protocol):
    def get(self, role: str, app_id: int) -> bytes | None: ...


class GitHubMissing(SafetyError):
    """Definitive HTTP 404, distinct from a timeout or other uncertain response."""


class GitHubHTTPFailure(SafetyError):
    def __init__(self, status: int, clock: str = "unknown") -> None:
        self.status = status
        self.clock = clock if clock in {"within_60s", "outside_60s"} else "unknown"
        super().__init__("GitHub HTTP request rejected")


class AppConnectionError(SafetyError):
    """Only bounded, credential-free authentication and permission facts escape."""

    def __init__(
        self,
        stage: str,
        reason: str,
        status: int | None = None,
        *,
        expected_permissions: dict[str, str] | None = None,
        actual_permissions: object = None,
        clock: str | None = None,
    ) -> None:
        stages = {"key", "installation", "token", "repository"}
        reasons = {
            "missing",
            "invalid",
            "http_rejected",
            "transport_or_response",
            "identity",
            "owner",
            "repository_selection",
            "suspended",
            "permissions",
            "repository_scope",
            "input_line_too_long",
            "matches_saved_review_key",
        }
        self.stage = stage if stage in stages else "unknown"
        self.reason = reason if reason in reasons else "unknown"
        self.status = status if type(status) is int and 100 <= status <= 599 else None
        self.permission_difference: dict[str, object] | None = None
        self.key_comparison: str | None = None
        self.clock = clock if clock in {"within_60s", "outside_60s", "unknown"} else None
        if expected_permissions is not None:
            self.permission_difference = permission_difference(
                expected_permissions, actual_permissions
            )
        super().__init__("App connection or scope validation failed")

    def public(self) -> dict[str, object]:
        report: dict[str, object] = {
            "authenticated": False,
            "stage": self.stage,
            "reason": self.reason,
            "http_status": self.status,
        }
        if self.permission_difference is not None:
            report["permission_difference"] = self.permission_difference
        if self.clock is not None:
            report["server_clock_comparison"] = self.clock
        if self.key_comparison in {"different_from_saved_review", "review_reference_unavailable"}:
            report["key_comparison"] = self.key_comparison
        return report


def server_clock_comparison(value: str | None, now: float) -> str:
    if not value or len(value) > 100:
        return "unknown"
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            return "unknown"
        return "within_60s" if abs(parsed.timestamp() - now) <= 60 else "outside_60s"
    except (ValueError, TypeError, OverflowError):
        return "unknown"


def permission_difference(expected: dict[str, str], actual: object) -> dict[str, object]:
    """Only known permission labels and finite access levels may be displayed."""
    known = {
        "contents",
        "checks",
        "pull_requests",
        "metadata",
        "administration",
        "actions",
        "issues",
    }
    if not isinstance(actual, dict):
        return {"response_shape": "invalid"}

    def level(values: dict[str, Any], name: str) -> str:
        if name not in values:
            return "absent"
        value = values[name]
        return value if isinstance(value, str) and value in {"read", "write"} else "unrecognized"

    differences: dict[str, object] = {}
    for name in sorted(known):
        want, have = level(expected, name), level(actual, name)
        if want != have:
            differences[name] = {"expected": want, "granted": have}
    unknown = len(set(actual) - known)
    if unknown:
        differences["other_permission_count"] = min(unknown, 1000)
    return differences


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def app_jwt(app_id: int, pem: bytes, now: int) -> str:
    if type(app_id) is not int or app_id <= 0:
        raise SafetyError("Invalid App identity")
    try:
        key = serialization.load_pem_private_key(pem, password=None)
        if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < 2048:
            raise SafetyError("RSA App key of at least 2048 bits required")
        header = _b64(b'{"alg":"RS256","typ":"JWT"}')
        payload = _b64(
            json.dumps(
                {"iat": now - 60, "exp": now + 480, "iss": str(app_id)}, separators=(",", ":")
            ).encode()
        )
        message = f"{header}.{payload}".encode("ascii")
        signature = key.sign(message, padding.PKCS1v15(), hashes.SHA256())
        return message.decode() + "." + _b64(signature)
    except (ValueError, TypeError):
        raise SafetyError("App key signing failed") from None


def github_request(
    method: str, path: str, bearer: str, document: dict[str, Any] | None = None
) -> Any:
    # A path cannot select another origin, encode traversal, inject a header or
    # leak credentials via a redirect. No environment-supplied endpoint/proxy.
    if (
        method not in {"GET", "POST", "PUT", "DELETE"}
        or not re.fullmatch(r"/[A-Za-z0-9_./?=&-]+", path)
        or ".." in path
        or "//" in path
        or not bearer
        or any(char.isspace() for char in bearer)
    ):
        raise SafetyError("Invalid GitHub request")
    request = urllib.request.Request(  # noqa: S310 — fixed HTTPS origin, validated path
        "https://api.github.com" + path,
        method=method,
        data=json.dumps(document).encode() if document is not None else None,
        headers={
            "Authorization": "Bearer " + bearer,
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Locus-App-Broker",
        },
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=20) as response:
            raw = response.read(1_000_001)
            if len(raw) > 1_000_000:
                raise SafetyError("GitHub response size limit")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        status = error.code
        clock = server_clock_comparison(
            error.headers.get("Date") if error.headers is not None else None, time.time()
        )
        error.close()
        if status == 404:
            raise GitHubMissing("GitHub object unavailable") from None
        raise GitHubHTTPFailure(status, clock) from None
    except (OSError, ValueError, urllib.error.URLError):
        # No exception chaining: URLError/HTTPError may include one-time paths,
        # response bodies or request objects. A write may have succeeded.
        raise SafetyError("GitHub request failed or uncertain; do not replay writes") from None


class GitHubApp:
    """No refresh/retry loop; tokens are handled in memory, not persisted.

    Issued tokens remain authorized until GitHub expiry/revocation. Dropping a
    Python reference is not revocation or a guaranteed memory wipe. Production
    activation still requires tested rotation/revocation and service isolation.

    App installation is explicitly selected and must expose exactly Locus with
    the approved role scopes. Additional repositories/privileges fail closed.
    """

    def __init__(
        self,
        role: str,
        app_id: int,
        installation: int,
        repository_id: int,
        vault: KeyReader,
        request: Callable[..., Any] = github_request,
    ) -> None:
        if role not in PERMISSIONS or any(
            type(value) is not int or value <= 0 for value in (app_id, installation, repository_id)
        ):
            raise SafetyError("Invalid App installation identity")
        self.role, self.app_id, self.installation = role, app_id, installation
        self.repository_id, self.vault, self.request = repository_id, vault, request

    def _fetch(
        self,
        stage: Literal["installation", "token", "repository"],
        method: str,
        path: str,
        bearer: str,
        document: dict[str, Any] | None = None,
    ) -> Any:
        try:
            if document is None:
                return self.request(method, path, bearer)
            return self.request(method, path, bearer, document)
        except GitHubMissing:
            if stage == "repository":
                raise  # The global mutex needs definitive absence, not a retry.
            raise AppConnectionError(stage, "http_rejected", 404) from None
        except GitHubHTTPFailure as error:
            raise AppConnectionError(
                stage,
                "http_rejected",
                error.status,
                clock=error.clock if error.status == 401 else None,
            ) from None
        except (SafetyError, OSError, ValueError):
            raise AppConnectionError(stage, "transport_or_response") from None

    def call(self, method: str, path: str, document: dict[str, Any] | None = None) -> Any:
        pem = self.vault.get(self.role, self.app_id)
        if pem is None:
            raise AppConnectionError("key", "missing")
        try:
            jwt = app_jwt(self.app_id, pem, int(time.time()))
        except SafetyError:
            raise AppConnectionError("key", "invalid") from None
        installation = self._fetch(
            "installation", "GET", f"/app/installations/{self.installation}", jwt
        )
        expected = {**PERMISSIONS[self.role], "metadata": "read"}
        if not isinstance(installation, dict) or installation.get("app_id") != self.app_id:
            raise AppConnectionError("installation", "identity")
        if installation.get("account", {}).get("login") != "kanalia7355":
            raise AppConnectionError("installation", "owner")
        if installation.get("repository_selection") != "selected":
            raise AppConnectionError("installation", "repository_selection")
        if installation.get("suspended_at") is not None:
            raise AppConnectionError("installation", "suspended")
        if installation.get("permissions") != expected:
            raise AppConnectionError(
                "installation",
                "permissions",
                expected_permissions=expected,
                actual_permissions=installation.get("permissions"),
            )
        result = self._fetch(
            "token",
            "POST",
            f"/app/installations/{self.installation}/access_tokens",
            jwt,
            {"repository_ids": [self.repository_id], "permissions": expected},
        )
        if not isinstance(result, dict):
            raise AppConnectionError("token", "transport_or_response")
        credential = result.get("token")
        if (
            not isinstance(credential, str)
            or not credential
            or result.get("permissions") != expected
            or result.get("repository_selection") != "selected"
            or [(repo.get("id"), repo.get("full_name")) for repo in result.get("repositories", [])]
            != [(self.repository_id, "kanalia7355/Locus")]
        ):
            raise AppConnectionError("token", "repository_scope")
        # Hard-bound to the selected repository; even a trusted caller cannot
        # accidentally use this primitive on another repository or GraphQL.
        if not path.startswith("/repos/kanalia7355/Locus/"):
            raise SafetyError("Repository-only App transport")
        return self._fetch("repository", method, path, credential, document)
