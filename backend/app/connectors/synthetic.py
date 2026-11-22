"""In-memory synthetic source connector: no network, no file I/O, test-editable."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from app.connectors.base import SourceObject


@dataclass
class _SyntheticObject:
    object_id: str
    revision: str
    name: str
    content: str
    readable_by: dict[str, bool] = field(default_factory=dict)


class SyntheticSourceConnector:
    """In-memory destination used by tests and local development only."""

    kind = "synthetic"

    def __init__(self, source_id: str = "synthetic-local") -> None:
        self.source_id = source_id
        self.objects: dict[str, _SyntheticObject] = {}

    def add(
        self,
        object_id: str,
        *,
        revision: str = "rev-1",
        name: str = "",
        content: str = "",
        readable_by: dict[str, bool] | None = None,
    ) -> None:
        self.objects[object_id] = _SyntheticObject(
            object_id=object_id,
            revision=revision,
            name=name,
            content=content,
            readable_by=dict(readable_by) if readable_by is not None else {},
        )

    def remove(self, object_id: str) -> None:
        self.objects.pop(object_id, None)

    def set_readable(self, object_id: str, user_id: str, allowed: bool) -> None:
        obj = self.objects.get(object_id)
        if obj is None:
            return
        obj.readable_by[user_id] = allowed

    def list_objects(self, source_id: str) -> list[SourceObject]:
        return [
            SourceObject(obj.object_id, obj.revision, obj.name, obj.content)
            for obj in self.objects.values()
        ]

    def read_object(self, source_id: str, object_id: str) -> str:
        obj = self.objects.get(object_id)
        if obj is None:
            raise KeyError(object_id)
        return obj.content

    def can_read(self, source_id: str, object_id: str, user_id: str) -> bool | None:
        obj = self.objects.get(object_id)
        if obj is None:
            # Unknown object: the source state is undecidable, so fail closed.
            return None
        return obj.readable_by.get(user_id)

    def permission_hash(self, source_id: str, object_id: str) -> str | None:
        obj = self.objects.get(object_id)
        if obj is None:
            return None
        payload = json.dumps(
            {"object_id": obj.object_id, "revision": obj.revision, "readable_by": obj.readable_by},
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def accepts_notifications(self) -> bool:
        # The in-memory connector can signal permission changes directly.
        return True
