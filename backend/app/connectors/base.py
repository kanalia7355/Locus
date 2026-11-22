"""Common interface for original-storage (source) connectors.

One destination kind implements this contract; the enforcement surface lives in
the service so every retrieval path shares it. The interface describes one source
object and the live per-user read decision plus a permission-relevant hash for
change detection. Raw credentials and ACL payloads are never part of it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SourceObject:
    """Stable opaque source identity with the connector-side revision."""

    object_id: str
    revision: str
    name: str
    content: str = ""


class SourceConnector(Protocol):
    """Contract for one original-storage destination (SMB / Drive / Box later)."""

    kind: str
    source_id: str

    def list_objects(self, source_id: str) -> list[SourceObject]: ...

    def read_object(self, source_id: str, object_id: str) -> str: ...

    def can_read(self, source_id: str, object_id: str, user_id: str) -> bool | None:
        """Whether the user may read this object now; None means "cannot decide"."""

    def permission_hash(self, source_id: str, object_id: str) -> str | None:
        """Hash of the permission-relevant state; None means "unknown"."""

    def accepts_notifications(self) -> bool:
        """Whether push permission-change notifications are supported."""
