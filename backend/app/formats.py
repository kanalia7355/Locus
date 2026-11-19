"""Accepted document formats declared as a single table.

One row declares one accepted format: its extension, kind, per-format byte
bound and extraction method name. The accepted-format table is the only place
that decides which document formats the backend accepts; the write path
(``app.service.upload``), the pre-ingestion report (``app.service.inventory``) and
the formats API (``GET /api/formats``) all read the same rows, so a format change
cannot leave one of them stale.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DocumentFormat:
    """One accepted format: extension, kind, byte bound and extraction method."""

    extension: str
    kind: str
    max_bytes: int
    extractor: str


# The one table to edit when the accepted format set changes. One row per
# accepted format; adding or removing a row moves upload, inventory and the
# formats API together. The default table keeps the original plain text formats
# only; real extraction adapters (PDF, Office, image OCR) are assigned by name
# here and land in later tasks.
SUPPORTED_FORMATS: list[DocumentFormat] = [
    DocumentFormat(extension=".txt", kind="text", max_bytes=262144, extractor="plaintext"),
    DocumentFormat(extension=".md", kind="text", max_bytes=262144, extractor="plaintext"),
    DocumentFormat(extension=".csv", kind="text", max_bytes=262144, extractor="plaintext"),
]


def accepted_extensions() -> frozenset[str]:
    """Lower-cased extensions (with leading dot) accepted by the current table."""
    return frozenset(row.extension.lower() for row in SUPPORTED_FORMATS)


def accepted_format_names() -> list[str]:
    """Bare lower-cased extension names accepted by the current table, in table order."""
    return [row.extension[1:] for row in SUPPORTED_FORMATS]


def max_content_bytes() -> int:
    """Largest per-format byte bound declared by the current table."""
    return max((row.max_bytes for row in SUPPORTED_FORMATS), default=0)


def format_for(name: str) -> DocumentFormat | None:
    """Return the table row matching a file name, or None when it is unsupported."""
    suffix = Path(name).suffix.lower()
    return next((row for row in SUPPORTED_FORMATS if row.extension == suffix), None)


def format_catalog() -> list[dict[str, Any]]:
    """Return the accepted-format table in the shape served by the formats API."""
    return [
        {
            "extension": row.extension,
            "kind": row.kind,
            "max_bytes": row.max_bytes,
            "extractor": row.extractor,
        }
        for row in SUPPORTED_FORMATS
    ]
