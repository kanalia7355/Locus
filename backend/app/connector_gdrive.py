"""Read-only Google Drive connector (service account, REST over httpx).

A sync selects one Drive folder through the connector's ``source`` (folder ID).
Credentials are a service-account JSON key named by
``LOCUS_GDRIVE_SERVICE_ACCOUNT_FILE``; the key is read into memory only and is
never written to a rejection, an exception message or a sync result.

The connector requests one scope only, ``drive.readonly``, and speaks the Drive
v3 REST API directly so the dependency lock stays unchanged. Change detection
uses ``headRevisionId`` through the T-STC-001 sync contract; the Changes API
page token is deliberately not used here.

A missing key file or folder ID raises ``GoogleDriveUnavailable`` instead of
returning an empty listing: an empty *complete* listing makes the sync engine
revoke every origin, which is right for "the folder is now empty" but wrong for
"this connector is not configured". A 403 during enumeration is the opposite
case -- the folder is reachable but no longer readable -- and is reported as an
empty complete listing so the existing origins are revoked.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import re
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from app.formats import format_for

KEY_FILE_ENV = "LOCUS_GDRIVE_SERVICE_ACCOUNT_FILE"
SCOPE = "https://www.googleapis.com/auth/drive.readonly"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 — OAuth2 endpoint URL, not a secret
FILES_URL = "https://www.googleapis.com/drive/v3/files"
LIST_FIELDS = "files(id,name,mimeType,md5Checksum,headRevisionId,size,modifiedTime),nextPageToken"
GOOGLE_APPS_PREFIX = "application/vnd.google-apps."
FOLDER_MIME = f"{GOOGLE_APPS_PREFIX}folder"
DOCUMENT_MIME = f"{GOOGLE_APPS_PREFIX}document"
SPREADSHEET_MIME = f"{GOOGLE_APPS_PREFIX}spreadsheet"
JWT_GRANT = "urn:ietf:params:oauth:grant-type:jwt-bearer"
TOKEN_LIFETIME_SECONDS = 3600
TOKEN_EXPIRY_SKEW_SECONDS = 60
REQUEST_TIMEOUT_SECONDS = 30.0
# Drive object IDs (folder and file alike) are base64url-ish; anything else is
# refused before it reaches a URL or a query string.
_DRIVE_ID = re.compile(r"^[A-Za-z0-9_-]+$")

REASON_CREDENTIALS_UNSET = "credentials_unset"
REASON_SOURCE_UNSET = "source_unset"
REASON_INVALID_SOURCE = "invalid_source"
REASON_INVALID_ITEM = "invalid_item"
REASON_FOLDER = "folder"
REASON_UNSUPPORTED_NATIVE = "unsupported_google_native"
REASON_UNSUPPORTED_FORMAT = "unsupported_format"
REASON_EXPORT_UNAVAILABLE = "export_unavailable"
REASON_SOURCE_UNREACHABLE = "source_unreachable"


class GoogleDriveError(RuntimeError):
    """Sanitized connector failure; never carries key material or response bodies."""


class GoogleDriveUnavailable(GoogleDriveError):
    """The connector is not configured; the source must not be treated as empty."""


def _sync_contract() -> Any:
    """Load the T-STC-001 sync contract module by path.

    ``app/connectors.py`` shares its name with the ``app/connectors/`` package,
    so it cannot be imported by module name. ``app.connector_local`` and
    ``app.service`` load it the same way for the same reason.
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


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _signed_assertion(client_email: str, private_key: Any, now: float) -> str:
    """RS256 JWT for the JWT bearer flow, scoped to read-only Drive."""

    header = {"alg": "RS256", "typ": "JWT"}
    claims = {
        "iss": client_email,
        "scope": SCOPE,
        "aud": TOKEN_URL,
        "iat": int(now),
        "exp": int(now) + TOKEN_LIFETIME_SECONDS,
    }
    signing_input = (
        f"{_b64url(json.dumps(header, separators=(',', ':')).encode('utf-8'))}."
        f"{_b64url(json.dumps(claims, separators=(',', ':')).encode('utf-8'))}"
    )
    signature = private_key.sign(signing_input.encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    return f"{signing_input}.{_b64url(signature)}"


def _load_service_account(path: Path) -> tuple[str, Any]:
    """Read the key file into memory; every failure is sanitized."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        raise GoogleDriveError("service account key file is not readable") from None
    except ValueError:
        raise GoogleDriveError("service account key file is not valid JSON") from None
    if not isinstance(payload, dict):
        raise GoogleDriveError("service account key file is not a JSON object")
    client_email = payload.get("client_email")
    private_key = payload.get("private_key")
    if not isinstance(client_email, str) or not client_email.strip():
        raise GoogleDriveError("service account key file has no client_email")
    if not isinstance(private_key, str) or not private_key.strip():
        raise GoogleDriveError("service account key file has no private_key")
    try:
        key = serialization.load_pem_private_key(private_key.encode("utf-8"), password=None)
    except (ValueError, TypeError, UnsupportedAlgorithm):
        raise GoogleDriveError("service account private_key is not usable") from None
    return client_email.strip(), key


def _import_name(name: str, suffix: str) -> str:
    """Normalize a Google-native item name to the export format's extension."""

    base = Path(name).stem.strip() or "document"
    return f"{base}{suffix}"


def _revision(entry: Mapping[str, Any]) -> str:
    """``headRevisionId`` first; Google-native files fall back to their mtime."""

    head = str(entry.get("headRevisionId") or "").strip()
    if head:
        return head
    modified = str(entry.get("modifiedTime") or "").strip()
    if modified:
        return f"modified:{modified}"
    checksum = str(entry.get("md5Checksum") or "").strip()
    if checksum:
        return f"md5:{checksum}"
    return ""


def _size(entry: Mapping[str, Any]) -> int:
    try:
        return max(int(str(entry.get("size") or "0")), 0)
    except ValueError:
        return 0


def _modified_at(entry: Mapping[str, Any]) -> float:
    value = str(entry.get("modifiedTime") or "").strip()
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


class GoogleDriveConnector:
    """One read-only Drive folder exposed through the T-STC-001 sync contract."""

    connector_id = "google_drive"
    kind = "google_drive"

    def __init__(
        self,
        source: str = "",
        *,
        key_file: str | Path | None = None,
        env: Mapping[str, str] | None = None,
        transport: httpx.BaseTransport | None = None,
        now: Callable[[], float] = time.time,
    ) -> None:
        environment = os.environ if env is None else env
        configured = key_file if key_file is not None else environment.get(KEY_FILE_ENV, "")
        text = str(configured).strip() if configured is not None else ""
        self.source = source.strip()
        self.rejections: list[Rejection] = []
        self.key_file = Path(text) if text else None
        self.configured = self.key_file is not None
        self._now = now
        self._client = httpx.Client(
            transport=transport,
            timeout=REQUEST_TIMEOUT_SECONDS,
            trust_env=False,
            follow_redirects=False,
        )
        self._credentials: tuple[str, Any] | None = None
        self._token: str | None = None
        self._token_expiry = 0.0
        # File ID -> export MIME type; None means "download the bytes as-is".
        self._exports: dict[str, str | None] = {}

    def close(self) -> None:
        self._client.close()

    def _record(self, external_id: str, reason: str, detail: str = "") -> None:
        self.rejections.append(Rejection(external_id=external_id, reason=reason, detail=detail))

    def _service_account(self) -> tuple[str, Any]:
        if not self.configured or self.key_file is None:
            raise GoogleDriveUnavailable("google drive service account key is not configured")
        if self._credentials is None:
            self._credentials = _load_service_account(self.key_file)
        return self._credentials

    def _access_token(self) -> str:
        """Cached bearer token; the assertion is signed only when it is stale."""

        now = self._now()
        if self._token is not None and now < self._token_expiry:
            return self._token
        client_email, private_key = self._service_account()
        assertion = _signed_assertion(client_email, private_key, now)
        try:
            response = self._client.post(
                TOKEN_URL,
                data={"grant_type": JWT_GRANT, "assertion": assertion},
            )
        except httpx.HTTPError:
            raise GoogleDriveError("google token request failed") from None
        if response.status_code != 200:
            raise GoogleDriveError(
                f"google token request failed with status {response.status_code}"
            )
        try:
            payload = response.json()
        except ValueError:
            raise GoogleDriveError("google token response was not JSON") from None
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token:
            raise GoogleDriveError("google token response carried no access token")
        try:
            lifetime = float(payload.get("expires_in", TOKEN_LIFETIME_SECONDS))
        except (TypeError, ValueError):
            lifetime = float(TOKEN_LIFETIME_SECONDS)
        self._token = token
        self._token_expiry = now + max(lifetime - TOKEN_EXPIRY_SKEW_SECONDS, 0.0)
        return token

    def _get(self, url: str, params: Mapping[str, str]) -> httpx.Response:
        """One authorized GET; a 401 refreshes the token exactly once."""

        token = self._access_token()
        try:
            response = self._client.get(
                url, params=dict(params), headers={"Authorization": f"Bearer {token}"}
            )
        except httpx.HTTPError:
            raise GoogleDriveError("google drive request failed") from None
        if response.status_code != 401:
            return response
        self._token = None
        self._token_expiry = 0.0
        token = self._access_token()
        try:
            return self._client.get(
                url, params=dict(params), headers={"Authorization": f"Bearer {token}"}
            )
        except httpx.HTTPError:
            raise GoogleDriveError("google drive request failed") from None

    def _item(self, entry: Any) -> Any | None:
        if not isinstance(entry, dict):
            self._record("", REASON_INVALID_ITEM)
            return None
        external_id = str(entry.get("id") or "").strip()
        if _DRIVE_ID.fullmatch(external_id) is None:
            self._record(external_id, REASON_INVALID_ITEM)
            return None
        name = str(entry.get("name") or "").strip()
        mime_type = str(entry.get("mimeType") or "").strip()
        if mime_type == FOLDER_MIME:
            self._record(external_id, REASON_FOLDER)
            return None
        export_mime: str | None = None
        import_name = name
        if mime_type.startswith(GOOGLE_APPS_PREFIX):
            if mime_type == DOCUMENT_MIME:
                export_mime = "text/plain"
                import_name = _import_name(name, ".txt")
            elif mime_type == SPREADSHEET_MIME:
                export_mime = "text/csv"
                import_name = _import_name(name, ".csv")
            else:
                self._record(external_id, REASON_UNSUPPORTED_NATIVE, mime_type)
                return None
        elif format_for(name) is None:
            self._record(external_id, REASON_UNSUPPORTED_FORMAT)
            return None
        self._exports[external_id] = export_mime
        # For Google-native items Drive's metadata size (when present) is not the
        # exported text byte length; SyncEngine checks the real exported bytes.
        item_size = 0 if export_mime is not None else _size(entry)
        return SourceItem(
            external_id=external_id,
            name=import_name,
            revision=_revision(entry),
            content_hash="",
            size=item_size,
            modified_at=_modified_at(entry),
        )

    def list_items(self, cursor: str | None = None) -> tuple[list[Any], str | None]:
        """Enumerate one page of direct children as metadata only."""

        if cursor is None:
            self.rejections.clear()
        folder = self.source
        if not folder:
            raise GoogleDriveUnavailable("google drive folder id is not configured")
        if _DRIVE_ID.fullmatch(folder) is None:
            self._record(folder, REASON_INVALID_SOURCE)
            raise GoogleDriveError("google drive folder id is not valid")
        params = {"q": f"'{folder}' in parents and trashed=false", "fields": LIST_FIELDS}
        if cursor:
            params["pageToken"] = cursor
        response = self._get(FILES_URL, params)
        if response.status_code == 403:
            # Initial folder listing 403 means the folder itself is no longer
            # shared/readable: report a complete empty listing so SyncEngine
            # revokes existing origins. On a later page, raise so SyncEngine
            # treats the partial listing as incomplete rather than revoking the
            # unobserved tail while keeping page 1.
            self._record(folder, REASON_SOURCE_UNREACHABLE, "forbidden")
            if cursor is None:
                return [], None
            raise GoogleDriveError("google drive folder became unreadable mid-pagination")
        if response.status_code != 200:
            raise GoogleDriveError(
                f"google drive listing failed with status {response.status_code}"
            )
        try:
            payload = response.json()
        except ValueError:
            raise GoogleDriveError("google drive listing response was not JSON") from None
        files = payload.get("files") if isinstance(payload, dict) else None
        if not isinstance(files, list):
            raise GoogleDriveError("google drive listing response carried no files")
        items = [item for entry in files if (item := self._item(entry)) is not None]
        next_cursor = payload.get("nextPageToken")
        if not isinstance(next_cursor, str) or not next_cursor:
            return items, None
        return items, next_cursor

    def fetch_content(self, external_id: str) -> bytes:
        """Download bytes, or the text export for a Google-native item."""

        if not self.configured:
            self._record(external_id, REASON_CREDENTIALS_UNSET)
            raise KeyError(external_id)
        if _DRIVE_ID.fullmatch(external_id) is None:
            self._record(external_id, REASON_INVALID_ITEM)
            raise KeyError(external_id)
        export_mime = self._exports.get(external_id)
        if export_mime is None:
            url = f"{FILES_URL}/{external_id}"
            params = {"alt": "media"}
        else:
            url = f"{FILES_URL}/{external_id}/export"
            params = {"mimeType": export_mime}
        response = self._get(url, params)
        if response.status_code == 401:
            raise GoogleDriveError("google drive rejected the access token")
        if response.status_code == 403 and export_mime is not None:
            # Drive returns 403 exportSizeLimitExceeded / cannotExportFile when a
            # Google-native item cannot be exported as text; return empty bytes so
            # SyncEngine counts the item as skipped rather than a connector error.
            self._record(external_id, REASON_EXPORT_UNAVAILABLE)
            return b""
        if response.status_code == 403:
            self._record(external_id, REASON_SOURCE_UNREACHABLE, "forbidden")
            raise GoogleDriveError("google drive denied access to an item")
        if response.status_code == 400 and export_mime is not None:
            self._record(external_id, REASON_EXPORT_UNAVAILABLE)
            return b""
        if response.status_code != 200:
            raise GoogleDriveError(
                f"google drive download failed with status {response.status_code}"
            )
        return response.content
