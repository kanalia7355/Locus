"""Common connector foundation for external storage sync.

This module defines the sync contract used by storage connectors and the
SyncEngine that registers source items into Locus documents. It is intentionally
self-contained so task-scoped tests can load it directly.
"""

from __future__ import annotations

import hashlib
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Protocol

from app.formats import format_for
from app.service import unsafe_document_name


@dataclass(frozen=True)
class SourceItem:
    """One item observed from an external source."""

    external_id: str
    name: str
    revision: str
    content_hash: str
    size: int
    modified_at: float


class ConnectorProtocol(Protocol):
    """Minimal contract for a storage connector."""

    def list_items(self, cursor: str | None = None) -> tuple[list[SourceItem], str | None]: ...

    def fetch_content(self, external_id: str) -> bytes: ...


class SyncEngine:
    """Synchronize connector items into documents and origin records.

    The engine never retains item content in failure/skip reports and never
    retries automatically; callers may run sync again later.
    """

    def __init__(self, service: Any) -> None:
        self._service = service

    def sync(
        self,
        actor: Any,
        project: str,
        connector: ConnectorProtocol,
        source_label: str,
        *,
        connector_id: str | None = None,
    ) -> dict[str, Any]:
        if connector_id is None:
            connector_id = str(
                getattr(connector, "connector_id", None)
                or getattr(connector, "source_id", None)
                or source_label
            )
        counts = {"registered": 0, "updated": 0, "skipped": 0, "failed": 0}
        reasons: dict[str, int] = {}
        seen_external_ids: set[str] = set()

        def skip(reason: str) -> None:
            counts["skipped"] += 1
            reasons[reason] = reasons.get(reason, 0) + 1

        def fail(reason: str) -> None:
            counts["failed"] += 1
            reasons[reason] = reasons.get(reason, 0) + 1

        cursor: str | None = None
        complete = False
        while True:
            try:
                items, cursor = connector.list_items(cursor)
            except Exception:
                fail("list_failed")
                break

            for item in items:
                external_id = str(getattr(item, "external_id", ""))
                if not external_id:
                    skip("invalid_item")
                    continue
                seen_external_ids.add(external_id)

                name = str(getattr(item, "name", ""))
                revision = str(getattr(item, "revision", ""))
                content_hash = str(getattr(item, "content_hash", ""))

                origin = self._service.get_document_origin(connector_id, external_id)
                if (
                    origin is not None
                    and origin["external_revision"] == revision
                    and not origin["revoked"]
                ):
                    skip("unchanged")
                    continue

                # Pre-filter using metadata where possible; content validation below
                # is authoritative and matches Service.upload.
                if unsafe_document_name(name) or format_for(name) is None:
                    skip("unsupported_format")
                    continue

                size = getattr(item, "size", None)
                doc_format = format_for(name)
                if doc_format is not None and isinstance(size, int) and size > doc_format.max_bytes:
                    skip("too_large")
                    continue

                try:
                    raw = connector.fetch_content(external_id)
                except Exception:
                    fail("fetch_failed")
                    continue

                if not isinstance(raw, (bytes, bytearray)):
                    skip("invalid_content")
                    continue

                if len(raw) > doc_format.max_bytes if doc_format else True:
                    skip("too_large")
                    continue

                try:
                    content = bytes(raw).decode("utf-8")
                except UnicodeDecodeError:
                    skip("invalid_encoding")
                    continue

                if not content.strip() or any(ord(c) < 32 and c not in "\n\r\t\f" for c in content):
                    skip("invalid_content")
                    continue

                computed_hash = content_hash or hashlib.sha256(bytes(raw)).hexdigest()
                try:
                    result = self._service.upload(actor, project, name, content, "personal")
                except Exception:
                    fail("upload_failed")
                    continue

                document_id = str(result["id"])
                try:
                    self._service.record_document_origin(
                        document_id=document_id,
                        connector_id=connector_id,
                        external_id=external_id,
                        external_revision=revision,
                        content_hash=computed_hash,
                        source_label=source_label,
                    )
                except Exception:
                    # The upload already committed, so a failed origin write would
                    # leave a document no origin row can update or revoke. Remove
                    # it and report the item as failed; the next sync imports it
                    # again, keeping "document exists" and "origin exists" in step.
                    # Rollback is best effort: a second failure must not abort the
                    # rest of the sync either.
                    with suppress(Exception):
                        self._service.delete_document(actor, document_id)
                    fail("origin_failed")
                    continue
                if origin is None or origin["revoked"]:
                    counts["registered"] += 1
                else:
                    counts["updated"] += 1

            if not cursor:
                complete = True
                break

        revoked = (
            self._service.revoke_missing_document_origins(connector_id, seen_external_ids)
            if complete
            else 0
        )
        counts["revoked"] = revoked
        counts["reasons"] = reasons
        return counts
