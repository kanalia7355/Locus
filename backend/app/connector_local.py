"""Read-only connector for a folder tree on the Locus host ("Explorer").

The administrator names one parent folder through ``LOCUS_LOCAL_SOURCE_ROOT``.
A sync request selects a relative sub-path under it through ``source``; absolute
paths, parent references and other escape shapes are refused. Enumeration is
metadata-only: the connector never opens a file to build an item, and
``content_hash`` is left empty for the sync engine to fill with SHA-256 when it
fetches the bytes.

Path safety reuses ``app.model_catalog`` (``local_volume``,
``checked_directories``, ``reparse``): the root and every traversed directory
must be local and free of reparse points, and links are never followed.
"""

from __future__ import annotations

import importlib.util
import os
import stat
import sys
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.connectors.smb import is_windows_reserved_name
from app.model_catalog import checked_directories, local_volume, reparse

ROOT_ENV = "LOCUS_LOCAL_SOURCE_ROOT"
MAX_DEPTH = 8
MAX_ITEMS = 1000

REASON_ROOT_UNSET = "root_not_configured"
REASON_PATH_ESCAPE = "path_escape"
REASON_SYMLINK = "symlink_or_junction"
REASON_DEPTH = "depth_limit"
REASON_ITEM_LIMIT = "item_limit"
REASON_NOT_FILE = "not_a_file"
REASON_UNREADABLE = "unreadable"


def _sync_contract() -> Any:
    """Load the T-STC-001 sync contract module by path.

    ``app/connectors.py`` shares its name with the ``app/connectors/`` package,
    so it cannot be imported by module name; ``app.service`` loads it the same
    way for the same reason.
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


def _configured_root(value: str | Path | None) -> Path | None:
    """Return the absolute local root, or None when the configuration is unusable."""

    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    path = Path(text)
    if not path.is_absolute() or text.startswith(("\\\\", "//")):
        return None
    return Path(os.path.abspath(path))


def _safe_relative(value: str) -> bool:
    """True for a non-empty relative path that stays inside the configured root."""

    if not isinstance(value, str) or not value:
        return False
    if "\x00" in value or any(ord(char) < 32 for char in value):
        return False
    normalized = value.replace("\\", "/")
    if normalized.startswith("/"):
        return False
    # Drive-qualified (C:) and alternate-data-stream forms both contain a colon.
    if len(normalized) >= 2 and normalized[1] == ":":
        return False
    if ":" in normalized:
        return False
    for segment in normalized.split("/"):
        if segment in {"", ".", ".."}:
            return False
        # Windows silently trims trailing dots and spaces, so these shapes can
        # alias a different name; refuse them instead of resolving them.
        if segment[-1] in {".", " "}:
            return False
        if any(char in '<>"|?*' for char in segment):
            return False
        if is_windows_reserved_name(segment):
            return False
    return True


def _within(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


class LocalFolderConnector:
    """One read-only folder tree exposed through the T-STC-001 sync contract."""

    connector_id = "local_folder"
    kind = "local_folder"

    def __init__(
        self,
        source: str = "",
        *,
        root: str | Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        environment = os.environ if env is None else env
        configured = root if root is not None else environment.get(ROOT_ENV, "")
        self.source = source
        self.rejections: list[Rejection] = []
        self.root = _configured_root(configured)
        self.configured = self.root is not None

    def _record(self, external_id: str, reason: str, detail: str = "") -> None:
        self.rejections.append(Rejection(external_id=external_id, reason=reason, detail=detail))

    @staticmethod
    def _relative(root: Path, path: Path) -> str:
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            return path.as_posix()

    def _select_target(self, root: Path) -> Path | None:
        """Root-relative ``source`` under the configured root, or None when refused."""

        if not self.source:
            return root
        if not _safe_relative(self.source):
            self._record(self.source, REASON_PATH_ESCAPE)
            return None
        target = Path(os.path.normpath(root / self.source))
        if not _within(root, target):
            self._record(self.source, REASON_PATH_ESCAPE)
            return None
        return target

    def list_items(self, cursor: str | None = None) -> tuple[list[Any], str | None]:
        """Enumerate regular files as metadata only; never read their bytes."""

        self.rejections.clear()
        root = self.root
        if root is None:
            self._record("", REASON_ROOT_UNSET)
            return [], None
        target = self._select_target(root)
        if target is None:
            return [], None
        try:
            if not local_volume(root):
                self._record(self.source, REASON_UNREADABLE, "nonlocal_volume")
                return [], None
            checked_directories(target)
        except (OSError, ValueError):
            self._record(self.source, REASON_UNREADABLE, "unsafe_root")
            return [], None

        items: list[Any] = []
        pending: deque[tuple[Path, int]] = deque([(target, 0)])
        while pending:
            directory, depth = pending.popleft()
            try:
                # Re-check the whole ancestor chain so a directory swapped for a
                # link after it was queued cannot be descended into.
                checked_directories(directory)
                with os.scandir(directory) as entries:
                    ordered = sorted(entries, key=lambda entry: entry.name)
            except (OSError, ValueError):
                self._record(self._relative(root, directory), REASON_UNREADABLE)
                continue
            for entry in ordered:
                path = Path(entry.path)
                external_id = self._relative(root, path)
                try:
                    if reparse(path):
                        self._record(external_id, REASON_SYMLINK)
                        continue
                    info = entry.stat(follow_symlinks=False)
                except OSError:
                    self._record(external_id, REASON_UNREADABLE)
                    continue
                if stat.S_ISDIR(info.st_mode):
                    if depth < MAX_DEPTH:
                        pending.append((path, depth + 1))
                    else:
                        self._record(external_id, REASON_DEPTH)
                    continue
                if not stat.S_ISREG(info.st_mode):
                    self._record(external_id, REASON_NOT_FILE)
                    continue
                if len(items) >= MAX_ITEMS:
                    self._record(external_id, REASON_ITEM_LIMIT)
                    return items, None
                items.append(
                    SourceItem(
                        external_id=external_id,
                        name=path.name,
                        revision=f"{info.st_mtime_ns}:{info.st_size}",
                        content_hash="",
                        size=info.st_size,
                        modified_at=info.st_mtime,
                    )
                )
        return items, None

    def fetch_content(self, external_id: str) -> bytes:
        """Read one file read-only after re-verifying it is under the root."""

        root = self.root
        if root is None:
            self._record(external_id, REASON_ROOT_UNSET)
            raise KeyError(external_id)
        if not _safe_relative(external_id):
            self._record(external_id, REASON_PATH_ESCAPE)
            raise KeyError(external_id)
        candidate = Path(os.path.normpath(root / external_id))
        if not _within(root, candidate):
            self._record(external_id, REASON_PATH_ESCAPE)
            raise KeyError(external_id)
        try:
            if not local_volume(root):
                raise ValueError("nonlocal_volume")
            checked_directories(candidate.parent)
        except (OSError, ValueError):
            self._record(external_id, REASON_UNREADABLE, "unsafe_root")
            raise KeyError(external_id) from None
        try:
            info = candidate.lstat()
            linked = reparse(candidate)
        except OSError:
            self._record(external_id, REASON_UNREADABLE)
            raise KeyError(external_id) from None
        if linked:
            self._record(external_id, REASON_SYMLINK)
            raise KeyError(external_id)
        if not stat.S_ISREG(info.st_mode):
            self._record(external_id, REASON_NOT_FILE)
            raise KeyError(external_id)
        # Re-check the resolved target so a swap between listing and fetch cannot
        # point the read outside the configured root.
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root.resolve(strict=True))
        except (OSError, RuntimeError, ValueError):
            self._record(external_id, REASON_PATH_ESCAPE)
            raise KeyError(external_id) from None
        try:
            with open(resolved, "rb") as handle:
                return handle.read()
        except OSError:
            self._record(external_id, REASON_UNREADABLE)
            raise KeyError(external_id) from None
