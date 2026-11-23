"""SMB (Windows shared folder) source connector.

The connector is offline-testable: a local temporary directory acts as the share
root in tests, and ACL readout is injected through a seam. ACL hashing,
effective-permission computation (most restrictive of share and file ACL) and
user mapping are pure functions outside the seam so every branch is testable with
synthetic input.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.connectors.base import SourceObject
from app.formats import format_for

logger = logging.getLogger(__name__)

# Windows reserved device names, case-insensitive, with or without extension.
_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

# Rejection reasons are recorded for observability; they are never surfaced as
# raw exception messages to end users.
REASON_PATH_ESCAPE = "path_escape"
REASON_SYMLINK = "symlink_or_junction"
REASON_OTHER_HOST = "other_host_unc"
REASON_RESERVED_NAME = "windows_reserved_name"
REASON_ADS = "alternate_data_stream"
REASON_OUT_OF_SCOPE = "out_of_scope"
REASON_UNREADABLE = "unreadable"
REASON_ACL_UNKNOWN = "acl_unknown"
REASON_UNMAPPED_USER = "unmapped_user"


@dataclass(frozen=True)
class ShareAcl:
    """Share-level ACL decisions keyed by Windows identity."""

    decisions: dict[str, bool | None]


@dataclass(frozen=True)
class FileAcl:
    """File-system ACL decisions keyed by Windows identity."""

    decisions: dict[str, bool | None]


@dataclass(frozen=True)
class AclSnapshot:
    """Permission-relevant ACL state for one source object."""

    share: ShareAcl
    file: FileAcl


class AclProvider(Protocol):
    """Seam for ACL readout. Production reads Windows ACLs; tests inject snapshots."""

    def get_snapshot(self, source_id: str, object_id: str) -> AclSnapshot | None:
        """Return the ACL snapshot for an object, or None when undecidable."""


@dataclass(frozen=True)
class Rejection:
    """Recorded refusal; observable by tests and operators, never silent."""

    object_id: str
    reason: str
    detail: str = ""


# --- Pure functions outside the ACL seam ---------------------------------


def effective_permission(share_decision: bool | None, file_decision: bool | None) -> bool | None:
    """Most-restrictive effective permission.

    Both sides must explicitly allow. If either side denies, is unknown, or is
    unobtainable, the result is not readable. Unknown is represented as None so
    callers can fail closed.
    """

    if share_decision is True and file_decision is True:
        return True
    if share_decision is False or file_decision is False:
        return False
    return None


def map_locus_user(username: str, user_mapping: dict[str, str]) -> str | None:
    """Explicit Locus username -> Windows identity mapping.

    No guessy name matching: only an exact configured mapping grants an identity.
    """

    return user_mapping.get(username)


def permission_hash_for_snapshot(snapshot: AclSnapshot) -> str:
    """Stable hash over permission-relevant ACL state."""

    payload = {
        "share": dict(sorted(snapshot.share.decisions.items())),
        "file": dict(sorted(snapshot.file.decisions.items())),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()


def is_windows_reserved_name(name: str) -> bool:
    """True for Windows device names, with or without extension."""

    base = name.split(".")[0].upper()
    return base in _RESERVED_NAMES


def has_alternate_data_stream(object_id: str) -> bool:
    """True when the object id contains an NTFS alternate data stream separator.

    A drive-letter colon (e.g. C:/...) is not an ADS; any other colon in the
    path/object id is rejected.
    """

    # Normalize to forward slashes for inspection; keep the raw characters.
    normalized = object_id.replace("\\", "/")
    # Strip a drive prefix like C: only when it is at position 0.
    if len(normalized) >= 2 and normalized[1] == ":" and normalized[0].isalpha():
        rest = normalized[2:]
    else:
        rest = normalized
    # UNC paths start with //; colons there are not drive letters.
    return ":" in rest


def has_other_host_unc(object_id: str, root: str) -> bool:
    """Reject UNC paths that point to a different host/share than the configured root."""

    raw = object_id
    if not (raw.startswith("\\\\") or raw.startswith("//")):
        return False
    root_norm = root.replace("/", "\\").lower().rstrip("\\")
    raw_norm = raw.replace("/", "\\").lower().rstrip("\\")
    # Same host/share prefix is allowed only if it stays under the configured root.
    return not raw_norm.startswith(root_norm + "\\") and raw_norm != root_norm


def contains_parent_ref(object_id: str) -> bool:
    """True when any path segment is a parent-directory reference."""

    normalized = object_id.replace("\\", "/")
    return any(segment == ".." for segment in normalized.split("/"))


def validate_object_id(object_id: str, root: str) -> str | None:
    """Return a rejection reason when object_id is unsafe, else None."""

    if not object_id or not isinstance(object_id, str):
        return REASON_PATH_ESCAPE
    if "\x00" in object_id or any(ord(ch) < 32 for ch in object_id):
        return REASON_PATH_ESCAPE
    if has_alternate_data_stream(object_id):
        return REASON_ADS
    if has_other_host_unc(object_id, root):
        return REASON_OTHER_HOST
    if contains_parent_ref(object_id):
        return REASON_PATH_ESCAPE
    # Check each component for reserved names.
    normalized = object_id.replace("\\", "/")
    for segment in normalized.split("/"):
        if not segment:
            continue
        if is_windows_reserved_name(segment):
            return REASON_RESERVED_NAME
    # Absolute paths or UNC that are not under root are escapes. Drive-rooted and
    # rooted paths are rejected unless they are exactly under the configured root.
    if os.path.isabs(object_id) or object_id.startswith("\\\\") or object_id.startswith("//"):
        root_norm = str(Path(root))
        obj_norm = str(Path(object_id))
        try:
            Path(obj_norm).resolve().relative_to(Path(root_norm).resolve())
        except Exception:
            return REASON_PATH_ESCAPE
    return None


def resolve_within_root(root: str, object_id: str) -> Path | None:
    """Resolve object_id under root, or None when it escapes/rejected.

    This is the single path-assembly point for UNC/local root differences.
    """

    reason = validate_object_id(object_id, root)
    if reason is not None:
        return None
    root_path = Path(root)
    # Build candidate: absolute/UNC object ids are allowed only when they already
    # point under root; relative ids are joined to root.
    candidate = Path(object_id) if os.path.isabs(object_id) else root_path / object_id
    try:
        resolved_root = root_path.resolve()
        # Use os.path.normpath-style absolute path without following a final
        # symlinked file target out of root by checking containment on the path
        # that keeps the final component, then resolve for comparisons.
        resolved_candidate = candidate.resolve()
    except Exception:
        return None
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError:
        return None
    return candidate


def is_reparse_point(path: Path) -> bool:
    """True for symlinks, junctions and other reparse points."""

    try:
        if path.is_symlink():
            return True
    except OSError:
        return True
    try:
        attrs = os.stat(path, follow_symlinks=False).st_file_attributes  # type: ignore[attr-defined]
    except AttributeError:
        # Non-Windows: st_file_attributes unavailable; symlink check above is enough.
        return False
    except OSError:
        return True
    # FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
    return bool(attrs & 0x0400)


def path_has_reparse_within(root: Path, candidate: Path) -> bool:
    """True when candidate or any existing component under root is a reparse point.

    Checks the unresolved path components so symlinks/junctions that point inside
    the root are still rejected.
    """

    try:
        resolved_root = root.resolve()
    except Exception:
        return True
    if is_reparse_point(resolved_root):
        return True
    # Work with the path as-given (no symlink following) for component checks.
    try:
        abs_candidate = candidate if candidate.is_absolute() else (resolved_root / candidate)
        normed = Path(os.path.normpath(str(abs_candidate)))
        relative = normed.relative_to(resolved_root)
    except Exception:
        # Also try normed root for cases where resolve changed representation.
        try:
            norm_root = Path(os.path.normpath(str(root)))
            if is_reparse_point(norm_root):
                return True
            abs_candidate = candidate if candidate.is_absolute() else (norm_root / candidate)
            normed = Path(os.path.normpath(str(abs_candidate)))
            relative = normed.relative_to(norm_root)
            resolved_root = norm_root
        except Exception:
            return True
    current = resolved_root
    for part in relative.parts:
        current = current / part
        if is_reparse_point(current):
            return True
    return False


# --- Windows ACL provider (seam implementation) ---------------------------
# This is the single place that would call Windows ACL APIs. It is intentionally
# isolated; tests inject a synthetic provider instead. If this method is broken,
# production SMB permission decisions become undecidable and the connector fails
# closed (no source objects become readable).


class WindowsAclProvider:
    """Production seam: reads share/file ACLs through Windows APIs.

    This class is not exercised by the offline test suite in this environment.
    """

    def get_snapshot(
        self, source_id: str, object_id: str
    ) -> AclSnapshot | None:  # pragma: no cover
        """Read ACLs using win32security when available.

        Isolated single Windows-API call site. Failures return None so callers
        fail closed.
        """

        try:
            import win32security  # type: ignore[import-not-found]

            # Placeholder for real ACL readout. The production implementation must
            # fill share and file decisions per mapped identity. Returning None
            # keeps the connector fail-closed until this is wired to a real share.
            _ = win32security
            return None
        except Exception:
            logger.warning(
                "smb acl read failed", extra={"source_id": source_id, "object_id": object_id}
            )
            return None


# --- Connector ------------------------------------------------------------


@dataclass
class _SmbObject:
    object_id: str
    revision: str
    name: str
    content: str


class SmbSourceConnector:
    """SMB source connector with injectable ACL seam and local-dir test mode."""

    kind = "smb"

    def __init__(
        self,
        source_id: str = "smb-share",
        *,
        root: str | Path | None = None,
        acl_provider: AclProvider | None = None,
        user_mapping: dict[str, str] | None = None,
    ) -> None:
        self.source_id = source_id
        self.root = str(root) if root is not None else ""
        self.acl_provider: AclProvider = (
            acl_provider if acl_provider is not None else WindowsAclProvider()
        )
        self.user_mapping: dict[str, str] = dict(user_mapping) if user_mapping is not None else {}
        self.rejections: list[Rejection] = []
        self._objects: dict[str, _SmbObject] = {}

    def _record_rejection(self, object_id: str, reason: str, detail: str = "") -> None:
        self.rejections.append(Rejection(object_id=object_id, reason=reason, detail=detail))
        logger.info(
            "smb object rejected",
            extra={"source_id": self.source_id, "object_id": object_id, "reason": reason},
        )

    def _resolve(self, object_id: str) -> Path | None:
        if not self.root:
            self._record_rejection(object_id, REASON_UNREADABLE, "root_not_configured")
            return None
        reason = validate_object_id(object_id, self.root)
        if reason is not None:
            self._record_rejection(object_id, reason)
            return None
        candidate = resolve_within_root(self.root, object_id)
        if candidate is None:
            self._record_rejection(object_id, REASON_PATH_ESCAPE)
            return None
        try:
            if path_has_reparse_within(Path(self.root), candidate):
                self._record_rejection(object_id, REASON_SYMLINK)
                return None
        except Exception:
            self._record_rejection(object_id, REASON_SYMLINK)
            return None
        return candidate

    def _object_revision(self, path: Path) -> str:
        try:
            st = path.stat()
        except OSError:
            return "missing"
        # Stable identity preference: NTFS file reference number when available.
        file_id = getattr(st, "st_ino", None)
        if file_id:
            return f"ino:{file_id}:{st.st_mtime_ns}:{st.st_size}"
        return f"stat:{st.st_mtime_ns}:{st.st_size}"

    def _read_text(self, path: Path, object_id: str) -> str | None:
        doc_format = format_for(path.name)
        if doc_format is None:
            self._record_rejection(object_id, REASON_OUT_OF_SCOPE, "unsupported_extension")
            return None
        try:
            size = path.stat().st_size
        except OSError:
            self._record_rejection(object_id, REASON_UNREADABLE, "stat_failed")
            return None
        if size > doc_format.max_bytes:
            self._record_rejection(object_id, REASON_OUT_OF_SCOPE, "too_large")
            return None
        try:
            raw = path.read_bytes()
        except OSError:
            self._record_rejection(object_id, REASON_UNREADABLE, "read_failed")
            return None
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            self._record_rejection(object_id, REASON_OUT_OF_SCOPE, "not_utf8")
            return None
        if not text.strip():
            self._record_rejection(object_id, REASON_OUT_OF_SCOPE, "empty")
            return None
        if any(ord(ch) < 32 and ch not in "\n\r\t\f" for ch in text):
            self._record_rejection(object_id, REASON_OUT_OF_SCOPE, "control_chars")
            return None
        return text

    def _scan_object(self, object_id: str) -> _SmbObject | None:
        candidate = self._resolve(object_id)
        if candidate is None:
            return None
        try:
            if not candidate.exists() or not candidate.is_file():
                return None
        except OSError:
            self._record_rejection(object_id, REASON_UNREADABLE, "exists_failed")
            return None
        content = self._read_text(candidate, object_id)
        if content is None:
            return None
        revision = self._object_revision(candidate)
        return _SmbObject(
            object_id=object_id, revision=revision, name=candidate.name, content=content
        )

    def list_objects(self, source_id: str) -> list[SourceObject]:
        self.rejections.clear()
        self._objects.clear()
        if not self.root:
            return []
        root = Path(self.root)
        try:
            if not root.exists():
                return []
        except OSError:
            return []
        objects: list[SourceObject] = []
        try:
            for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
                dir_path = Path(dirpath)
                # Prune reparse-point/symlink directories so we never descend.
                kept: list[str] = []
                for dirname in sorted(dirnames):
                    child = dir_path / dirname
                    try:
                        rel_dir = child.relative_to(root).as_posix()
                    except Exception:
                        rel_dir = str(child)
                    if is_reparse_point(child):
                        self._record_rejection(rel_dir, REASON_SYMLINK)
                        continue
                    kept.append(dirname)
                dirnames[:] = kept
                for filename in sorted(filenames):
                    path = dir_path / filename
                    try:
                        rel = path.relative_to(root).as_posix()
                    except Exception:
                        self._record_rejection(str(path), REASON_PATH_ESCAPE)
                        continue
                    if is_reparse_point(path):
                        self._record_rejection(rel, REASON_SYMLINK)
                        continue
                    obj = self._scan_object(rel)
                    if obj is None:
                        continue
                    self._objects[rel] = obj
                    objects.append(SourceObject(obj.object_id, obj.revision, obj.name, obj.content))
        except OSError:
            return objects
        return objects

    def read_object(self, source_id: str, object_id: str) -> str:
        obj = self._objects.get(object_id)
        if obj is not None:
            return obj.content
        scanned = self._scan_object(object_id)
        if scanned is None:
            raise KeyError(object_id)
        self._objects[object_id] = scanned
        return scanned.content

    def _snapshot(self, object_id: str) -> AclSnapshot | None:
        reason = validate_object_id(object_id, self.root)
        if reason is not None:
            self._record_rejection(object_id, reason)
            return None
        if self.root:
            candidate = resolve_within_root(self.root, object_id)
            if candidate is None:
                self._record_rejection(object_id, REASON_PATH_ESCAPE)
                return None
            try:
                if path_has_reparse_within(Path(self.root), candidate):
                    self._record_rejection(object_id, REASON_SYMLINK)
                    return None
            except Exception:
                self._record_rejection(object_id, REASON_SYMLINK)
                return None
        try:
            return self.acl_provider.get_snapshot(self.source_id, object_id)
        except Exception:
            logger.warning(
                "smb acl snapshot failed",
                extra={"source_id": self.source_id, "object_id": object_id},
            )
            return None

    def can_read(self, source_id: str, object_id: str, user_id: str) -> bool | None:
        identity = map_locus_user(user_id, self.user_mapping)
        if identity is None:
            self._record_rejection(object_id, REASON_UNMAPPED_USER)
            return False
        snapshot = self._snapshot(object_id)
        if snapshot is None:
            return None
        share_decision = snapshot.share.decisions.get(identity)
        file_decision = snapshot.file.decisions.get(identity)
        decision = effective_permission(share_decision, file_decision)
        if decision is True:
            return True
        return False if decision is False else None

    def permission_hash(self, source_id: str, object_id: str) -> str | None:
        snapshot = self._snapshot(object_id)
        if snapshot is None:
            return None
        return permission_hash_for_snapshot(snapshot)

    def accepts_notifications(self) -> bool:
        return False
