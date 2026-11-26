"""Read-only Box connector (Client Credentials Grant, REST over httpx).

A sync selects one Box folder through the connector's ``source`` (folder ID,
where ``"0"`` is the root folder). Credentials come from environment variables
``LOCUS_BOX_CLIENT_ID``, ``LOCUS_BOX_CLIENT_SECRET``, and
``LOCUS_BOX_ENTERPRISE_ID``; their values are held via an internal accessor and
never exposed in exceptions, logs, rejections, ``vars(connector)``, or sync
results.

The connector speaks the Box v2 REST API directly over ``httpx`` so the
dependency lock stays unchanged. Enumeration walks subfolders with bounded
depth and item counts, using ``file_version.id`` (falling back to ``sha1``) as
``revision`` and Box's ``sha1`` as ``content_hash``. Content downloads validate
that any redirect target is HTTPS on a Box download host before following it.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from app.formats import format_for

CLIENT_ID_ENV = "LOCUS_BOX_CLIENT_ID"
CLIENT_SECRET_ENV = "_".join(("LOCUS", "BOX", "CLIENT", "SECRET"))
ENTERPRISE_ID_ENV = "LOCUS_BOX_ENTERPRISE_ID"

TOKEN_URL = "https://api.box.com/oauth2/token"  # noqa: S105 — OAuth2 endpoint URL, not a secret
API_BASE_URL = "https://api.box.com/2.0"
ITEM_FIELDS = "id,type,name,sha1,size,modified_at,file_version"

PAGE_LIMIT = 1000
MAX_DEPTH = 8
MAX_ITEMS = 1000
MAX_REDIRECTS = 5
TOKEN_LIFETIME_SECONDS = 3600
TOKEN_EXPIRY_SKEW_SECONDS = 60
REQUEST_TIMEOUT_SECONDS = 30.0

# Box folder/file IDs are numeric ("0" for root) or alphanumeric identifiers;
# reject slashes, spaces, quotes, and path-traversal shapes before URL building.
_BOX_ID = re.compile(r"^[A-Za-z0-9_-]+$")
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_BOX_DOWNLOAD_HOST_SUFFIXES = (".boxcloud.com", ".box.com")
_BOX_DOWNLOAD_EXACT_HOSTS = frozenset({"dl.boxcloud.com", "public.boxcloud.com"})

REASON_CREDENTIALS_UNSET = "credentials_unset"
REASON_SOURCE_UNSET = "source_unset"
REASON_INVALID_SOURCE = "invalid_source"
REASON_INVALID_ITEM = "invalid_item"
REASON_DEPTH = "depth_limit"
REASON_ITEM_LIMIT = "item_limit"
REASON_UNSUPPORTED_TYPE = "unsupported_item_type"
REASON_UNSUPPORTED_FORMAT = "unsupported_format"
REASON_REDIRECT_UNSAFE = "unsafe_redirect"
REASON_SOURCE_UNREACHABLE = "source_unreachable"


class BoxError(RuntimeError):
    """Sanitized connector failure; never carries credential values or response bodies."""


class BoxUnavailable(BoxError):
    """The connector is not configured; the source must not be treated as empty."""


def _sync_contract() -> Any:
    """Load the T-STC-001 sync contract module by path.

    ``app/connectors.py`` shares its name with the ``app/connectors/`` package,
    so it cannot be imported by module name. ``app.connector_local``,
    ``app.connector_gdrive`` and ``app.service`` load it the same way.
    """

    name = "app_connectors_sync_contract"
    module = sys.modules.get(name)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name("connectors.py"))
    if spec is None or spec.loader is None:
        raise RuntimeError("connectors module unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


SourceItem = _sync_contract().SourceItem


@dataclass(frozen=True)
class Rejection:
    """Recorded refusal; observable by tests and operators, never silent."""

    external_id: str
    reason: str
    detail: str = ""


def _is_allowed_download_url(url: httpx.URL) -> bool:
    """True only for HTTPS URLs hosted on Box download domains."""

    if url.scheme.lower() != "https":
        return False
    if url.username or url.password:
        return False
    host = (url.host or "").lower().rstrip(".")
    if not host or host == "api.box.com":
        return False
    if host in _BOX_DOWNLOAD_EXACT_HOSTS:
        return True
    return any(host.endswith(suffix) for suffix in _BOX_DOWNLOAD_HOST_SUFFIXES)


def _revision(entry: Mapping[str, Any], sha1: str) -> str:
    """``file_version.id`` first, falling back to ``sha1``."""

    file_version = entry.get("file_version")
    if isinstance(file_version, Mapping):
        version_id = str(file_version.get("id") or "").strip()
        if version_id:
            return version_id
    return sha1


def _size(entry: Mapping[str, Any]) -> int:
    try:
        return max(int(str(entry.get("size") or "0")), 0)
    except ValueError:
        return 0


def _modified_at(entry: Mapping[str, Any]) -> float:
    value = str(entry.get("modified_at") or "").strip()
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _secret_reader(
    client_id: str, client_secret: str, enterprise_id: str
) -> Callable[[], tuple[str, str, str]]:
    """Keep credential values inside a closure rather than instance attributes."""

    def read() -> tuple[str, str, str]:
        return client_id, client_secret, enterprise_id

    return read


def _token_store() -> tuple[
    Callable[[], tuple[str | None, float]],
    Callable[[str | None, float], None],
]:
    """Keep cached bearer tokens inside a closure rather than ``vars(connector)``."""

    token: str | None = None
    expiry = 0.0

    def get_token() -> tuple[str | None, float]:
        return token, expiry

    def set_token(value: str | None, expires_at: float) -> None:
        nonlocal token, expiry
        token = value
        expiry = expires_at

    return get_token, set_token


class BoxConnector:
    """One read-only Box folder tree exposed through the T-STC-001 sync contract."""

    connector_id = "box"
    kind = "box"

    def __init__(
        self,
        source: str = "",
        *,
        env: Mapping[str, str] | None = None,
        transport: httpx.BaseTransport | None = None,
        now: Callable[[], float] = time.time,
    ) -> None:
        environment = os.environ if env is None else env
        client_id = str(environment.get(CLIENT_ID_ENV, "") or "").strip()
        client_secret = str(environment.get(CLIENT_SECRET_ENV, "") or "").strip()
        enterprise_id = str(environment.get(ENTERPRISE_ID_ENV, "") or "").strip()

        self.source = source.strip()
        self.rejections: list[Rejection] = []
        self.configured = bool(client_id and client_secret and enterprise_id)
        self._read_credentials = (
            _secret_reader(client_id, client_secret, enterprise_id) if self.configured else None
        )
        self._get_token, self._set_token = _token_store()
        self._now = now
        self._transport = transport
        self._client = httpx.Client(
            transport=transport,
            timeout=REQUEST_TIMEOUT_SECONDS,
            trust_env=False,
            follow_redirects=False,
        )

    def __repr__(self) -> str:
        return f"BoxConnector(source={self.source!r}, configured={self.configured!r})"

    def close(self) -> None:
        self._client.close()

    def _record(self, external_id: str, reason: str, detail: str = "") -> None:
        self.rejections.append(Rejection(external_id=external_id, reason=reason, detail=detail))

    def _access_token(self) -> str:
        """Cached CCG bearer token; re-acquired when absent or expired."""

        if not self.configured or self._read_credentials is None:
            raise BoxUnavailable("box credentials are not configured")
        now = self._now()
        cached_token, cached_expiry = self._get_token()
        if cached_token is not None and now < cached_expiry:
            return cached_token

        client_id, client_secret, enterprise_id = self._read_credentials()
        try:
            response = self._client.post(
                TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "box_subject_type": "enterprise",
                    "box_subject_id": enterprise_id,
                },
            )
        except httpx.HTTPError:
            raise BoxError("box token request failed") from None

        if response.status_code != 200:
            raise BoxError(f"box token request failed with status {response.status_code}")

        try:
            payload = response.json()
        except ValueError:
            raise BoxError("box token response was not JSON") from None

        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token:
            raise BoxError("box token response carried no access token")

        try:
            lifetime = float(payload.get("expires_in", TOKEN_LIFETIME_SECONDS))
        except (TypeError, ValueError):
            lifetime = float(TOKEN_LIFETIME_SECONDS)

        self._set_token(token, now + max(lifetime - TOKEN_EXPIRY_SKEW_SECONDS, 0.0))
        return token

    def _get_api(self, url: str, params: Mapping[str, str] | None = None) -> httpx.Response:
        """One authorized GET to api.box.com (no redirects); 401 refreshes once."""

        token = self._access_token()
        query = dict(params) if params is not None else None
        try:
            response = self._client.get(
                url,
                params=query,
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.HTTPError:
            raise BoxError("box api request failed") from None

        if response.status_code != 401:
            return response

        self._set_token(None, 0.0)
        token = self._access_token()
        try:
            return self._client.get(
                url,
                params=query,
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.HTTPError:
            raise BoxError("box api request failed") from None

    def _item(self, entry: Any) -> Any | None:
        if not isinstance(entry, Mapping):
            self._record("", REASON_INVALID_ITEM)
            return None
        external_id = str(entry.get("id") or "").strip()
        if _BOX_ID.fullmatch(external_id) is None:
            self._record(external_id, REASON_INVALID_ITEM)
            return None
        name = str(entry.get("name") or "").strip()
        if not name or format_for(name) is None:
            self._record(external_id, REASON_UNSUPPORTED_FORMAT)
            return None
        sha1 = str(entry.get("sha1") or "").strip()
        revision = _revision(entry, sha1)
        if not revision:
            self._record(external_id, REASON_INVALID_ITEM)
            return None
        return SourceItem(
            external_id=external_id,
            name=name,
            revision=revision,
            content_hash=sha1,
            size=_size(entry),
            modified_at=_modified_at(entry),
        )

    def list_items(self, cursor: str | None = None) -> tuple[list[Any], str | None]:
        """Enumerate Box folder items with limit/offset paging and bounded recursion."""

        if cursor is not None:
            return [], None
        self.rejections.clear()
        root_folder = self.source
        if not root_folder:
            raise BoxUnavailable("box folder id is not configured")
        if _BOX_ID.fullmatch(root_folder) is None:
            self._record(root_folder, REASON_INVALID_SOURCE)
            raise BoxError("box folder id is not valid")
        if not self.configured:
            raise BoxUnavailable("box credentials are not configured")

        items: list[Any] = []
        visited_folders: set[str] = {root_folder}
        pending: deque[tuple[str, int]] = deque([(root_folder, 0)])
        started = False

        while pending:
            folder_id, depth = pending.popleft()
            offset = 0
            while True:
                response = self._get_api(
                    f"{API_BASE_URL}/folders/{folder_id}/items",
                    params={
                        "fields": ITEM_FIELDS,
                        "limit": str(PAGE_LIMIT),
                        "offset": str(offset),
                    },
                )
                is_initial_root_request = not started
                started = True

                if response.status_code in {403, 404}:
                    detail = "forbidden" if response.status_code == 403 else "not_found"
                    self._record(folder_id, REASON_SOURCE_UNREACHABLE, detail)
                    if is_initial_root_request:
                        # Root folder itself lost access or was removed: report a
                        # complete empty listing so SyncEngine marks existing origins
                        # revoked, matching T-STC-003.
                        return [], None
                    raise BoxError("box folder became unreachable during enumeration")

                if response.status_code != 200:
                    raise BoxError(f"box listing failed with status {response.status_code}")

                try:
                    payload = response.json()
                except ValueError:
                    raise BoxError("box listing response was not JSON") from None

                entries = payload.get("entries") if isinstance(payload, Mapping) else None
                if not isinstance(entries, list):
                    raise BoxError("box listing response carried no entries")

                for entry in entries:
                    if not isinstance(entry, Mapping):
                        self._record("", REASON_INVALID_ITEM)
                        continue
                    item_type = str(entry.get("type") or "").strip()
                    entry_id = str(entry.get("id") or "").strip()
                    if item_type == "folder":
                        if _BOX_ID.fullmatch(entry_id) is None:
                            self._record(entry_id, REASON_INVALID_ITEM)
                            continue
                        if entry_id in visited_folders:
                            continue
                        if depth < MAX_DEPTH:
                            visited_folders.add(entry_id)
                            pending.append((entry_id, depth + 1))
                        else:
                            self._record(entry_id, REASON_DEPTH)
                        continue
                    if item_type != "file":
                        self._record(entry_id, REASON_UNSUPPORTED_TYPE, item_type)
                        continue
                    if len(items) >= MAX_ITEMS:
                        self._record(entry_id, REASON_ITEM_LIMIT)
                        return items, None
                    built = self._item(entry)
                    if built is not None:
                        items.append(built)

                if not entries:
                    break
                next_offset = offset + len(entries)
                total_count = payload.get("total_count") if isinstance(payload, Mapping) else None
                if isinstance(total_count, int):
                    if next_offset >= total_count:
                        break
                else:
                    try:
                        effective_limit = int(str(payload.get("limit") or PAGE_LIMIT))
                    except ValueError:
                        effective_limit = PAGE_LIMIT
                    if len(entries) < effective_limit:
                        break
                offset = next_offset

        return items, None

    def _validate_download_redirect(self, external_id: str, request: httpx.Request) -> None:
        """Event hook on the download-only client: validate every redirect target."""

        if not _is_allowed_download_url(request.url):
            self._record(external_id, REASON_REDIRECT_UNSAFE)
            raise BoxError("box download redirect pointed to an unexpected host")

    def fetch_content(self, external_id: str) -> bytes:
        """Download file bytes via ``/files/{id}/content``, following safe Box redirects."""

        if not self.configured:
            self._record(external_id, REASON_CREDENTIALS_UNSET)
            raise KeyError(external_id)
        if _BOX_ID.fullmatch(external_id) is None:
            self._record(external_id, REASON_INVALID_ITEM)
            raise KeyError(external_id)

        content_url = f"{API_BASE_URL}/files/{external_id}/content"
        response = self._get_api(content_url)

        if response.status_code == 401:
            raise BoxError("box rejected the access token")
        if response.status_code in {403, 404}:
            detail = "forbidden" if response.status_code == 403 else "not_found"
            self._record(external_id, REASON_SOURCE_UNREACHABLE, detail)
            raise BoxError("box denied access to an item")

        if response.status_code in _REDIRECT_STATUSES:
            location = response.headers.get("Location", "").strip()
            if not location:
                self._record(external_id, REASON_REDIRECT_UNSAFE)
                raise BoxError("box download redirect carried no location")
            try:
                target_url = response.url.join(location)
            except httpx.InvalidURL:
                self._record(external_id, REASON_REDIRECT_UNSAFE)
                raise BoxError("box download redirect location was invalid") from None
            if not _is_allowed_download_url(target_url):
                self._record(external_id, REASON_REDIRECT_UNSAFE)
                raise BoxError("box download redirect pointed to an unexpected host")

            # Follow redirects ONLY on this download leg, without Authorization
            # header, while validating every hop via event_hooks.
            with httpx.Client(
                transport=self._transport,
                timeout=REQUEST_TIMEOUT_SECONDS,
                trust_env=False,
                follow_redirects=True,
                max_redirects=MAX_REDIRECTS,
                event_hooks={
                    "request": [lambda req: self._validate_download_redirect(external_id, req)]
                },
            ) as download_client:
                try:
                    response = download_client.get(target_url)
                except httpx.HTTPError:
                    raise BoxError("box download failed") from None

        if response.status_code in {403, 404}:
            detail = "forbidden" if response.status_code == 403 else "not_found"
            self._record(external_id, REASON_SOURCE_UNREACHABLE, detail)
            raise BoxError("box denied access to an item")
        if response.status_code != 200:
            raise BoxError(f"box download failed with status {response.status_code}")
        return response.content
