"""Short-lived repo-only installation credentials; fixed HTTPS origin, no CLI."""

import base64
import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any, Protocol

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from loop_engine.app_onboarding import PERMISSIONS, _NoRedirect
from loop_engine.security import SafetyError


class KeyReader(Protocol):
    def get(self, role: str, app_id: int) -> bytes | None: ...


class GitHubMissing(SafetyError):
    """Definitive HTTP 404, distinct from a timeout or other uncertain response."""


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
        error.close()
        if status == 404:
            raise GitHubMissing("GitHub object unavailable") from None
        raise SafetyError("GitHub request rejected; do not replay writes") from None
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

    def call(self, method: str, path: str, document: dict[str, Any] | None = None) -> Any:
        pem = self.vault.get(self.role, self.app_id)
        if pem is None:
            raise SafetyError("App credential missing")
        jwt = app_jwt(self.app_id, pem, int(time.time()))
        installation = self.request("GET", f"/app/installations/{self.installation}", jwt)
        expected = {**PERMISSIONS[self.role], "metadata": "read"}
        if (
            installation.get("app_id") != self.app_id
            or installation.get("account", {}).get("login") != "kanalia7355"
            or installation.get("repository_selection") != "selected"
            or installation.get("suspended_at") is not None
            or installation.get("permissions") != expected
        ):
            raise SafetyError("App installation scope not approved")
        result = self.request(
            "POST",
            f"/app/installations/{self.installation}/access_tokens",
            jwt,
            {"repository_ids": [self.repository_id], "permissions": PERMISSIONS[self.role]},
        )
        credential = result.get("token")
        if (
            not isinstance(credential, str)
            or not credential
            or result.get("permissions") != expected
            or result.get("repository_selection") != "selected"
            or [(repo.get("id"), repo.get("full_name")) for repo in result.get("repositories", [])]
            != [(self.repository_id, "kanalia7355/Locus")]
        ):
            raise SafetyError("Installation credential response scope rejected")
        # Hard-bound to the selected repository; even a trusted caller cannot
        # accidentally use this primitive on another repository or GraphQL.
        if not path.startswith("/repos/kanalia7355/Locus/"):
            raise SafetyError("Repository-only App transport")
        return self.request(method, path, credential, document)
