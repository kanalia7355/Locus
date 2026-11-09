"""Retained metadata handles for one trial arg0 path; never file data or repair."""

import ctypes
import re
from collections.abc import Callable
from ctypes import wintypes as w
from pathlib import Path
from typing import Any

from loop_engine.auth_file_profile import _Info, private_acl
from loop_engine.security import SafetyError, reparse
from loop_engine.windows_pipe import Native


class Arg0Guard:
    def __init__(
        self,
        home: Path,
        sid: str,
        remaining: Callable[[], Any] = lambda: None,
        *,
        runtime_acl: Any = None,
    ) -> None:
        from loop_engine.runtime_acl import RuntimeAcl

        self.runtime = RuntimeAcl(home, sid, runtime_acl) if runtime_acl is not None else None
        self.home, self.sid = home, sid
        self.root = home / "tmp/arg0-windows"
        self.native = Native()
        self.handles: list[Any] = []
        self.bound: tuple[Path, list[Any]] | None = None
        self.before: set[str] = set()
        self.before_ids: set[int] = set()
        self.remaining = remaining
        self.remaining()
        if any(reparse(p) for p in (self.root, *self.root.parents)):
            raise SafetyError("Arg0 namespace traverses reparse boundary")
        if self.root.exists():
            for count, child in enumerate(self.root.iterdir(), 1):
                self.remaining()
                if count > 256 or reparse(child):
                    raise SafetyError("Arg0 namespace is unassessed")
                self.before.add(child.name)
                self.before_ids.add(child.stat(follow_symlinks=False).st_ino)
        try:
            if not home.is_dir():
                raise SafetyError("Existing arg0 home is missing")
            for parent in (home, home / "tmp", self.root):
                if parent.exists():
                    self._open(parent, True)
        except BaseException:
            self.close()
            raise

    def _open(self, path: Path, directory: bool) -> tuple[Any, dict[str, Any]]:
        self.remaining()
        if any(reparse(p) for p in (path, *path.parents)):
            raise SafetyError("Arg0 reparse boundary")
        k = self.native.kernel
        k.GetDriveTypeW.argtypes, k.GetDriveTypeW.restype = [w.LPCWSTR], w.UINT
        if not re.fullmatch(r"[A-Za-z]:", path.drive) or k.GetDriveTypeW(path.anchor) != 3:
            raise SafetyError("Arg0 local fixed drive required")
        handle = k.CreateFileW(str(path), 0x20080, 3, None, 3, 0x2200000, None)
        if handle == ctypes.c_void_p(-1).value:
            raise SafetyError("Arg0 metadata unavailable")
        self.handles.append(handle)
        k.GetFileInformationByHandle.argtypes = [w.HANDLE, ctypes.POINTER(_Info)]
        k.GetFileInformationByHandle.restype = w.BOOL
        k.GetFinalPathNameByHandleW.argtypes = [w.HANDLE, w.LPWSTR, w.DWORD, w.DWORD]
        k.GetFinalPathNameByHandleW.restype = w.DWORD
        info, final = _Info(), ctypes.create_unicode_buffer(32768)
        length = k.GetFinalPathNameByHandleW(handle, final, len(final), 0)
        if (
            not k.GetFileInformationByHandle(handle, ctypes.byref(info))
            or not 0 < length < len(final)
            or final.value != "\\\\?\\" + str(path)
            or bool(info.attributes & 16) != directory
            or info.attributes & ~(0x1 | 0x2 | 0x4 | 0x10 | 0x20 | 0x80 | 0x800 | 0x2000 | 0x4000)
            or info.links != 1
            or not (info.index_low | info.index_high)
            or (not directory and (info.size_high or info.size_low > 65536))
        ):
            raise SafetyError("Arg0 path/attribute identity differs")
        security = self.native.security(handle, kind=1)
        if self.runtime is None:
            private_acl(security, self.sid)
        else:
            self.runtime.validate(path, directory, security)
        identity = {
            "volume": info.volume,
            "index": info.index_low | info.index_high << 32,
            "created": info.created.low | info.created.high << 32,
            "attributes": info.attributes,
            "security": security,
        }
        return handle, identity

    def check(self, text: str, low: float, high: float) -> dict[str, Any]:
        path = Path(text)
        if (
            str(path) != text
            or path.parent != self.root
            or not re.fullmatch(r"codex-arg0[A-Za-z0-9]{6}", path.name)
            or path.name in self.before
        ):
            raise SafetyError("Arg0 path is not a fresh exact invocation path")
        # One capture plus one bounded recheck; never follow another candidate.
        observed = []
        base = len(self.handles)
        recheck = self.bound is not None
        try:
            for parent in (self.home, self.home / "tmp", self.root):
                _, metadata = self._open(parent, True)
                observed.append(metadata)
            _, metadata = self._open(path, True)
            created = metadata["created"] / 10_000_000 - 11644473600
            if not low <= created <= high or metadata["index"] in self.before_ids:
                raise SafetyError("Stale arg0 creation time")
            observed.append(metadata)
            names = set()
            for child in path.iterdir():
                self.remaining()
                names.add(child.name)
                if len(names) > 3:
                    raise SafetyError("Unknown arg0 child")
            if names != {".lock", "apply_patch.bat", "applypatch.bat"}:
                raise SafetyError("Unknown arg0 child")
            for name in (".lock", "apply_patch.bat", "applypatch.bat"):
                _, metadata = self._open(path / name, False)
                observed.append(metadata)
            if self.bound is not None and self.bound != (path, observed):
                raise SafetyError("Arg0 identity changed before reservation")
            self.bound = (path, observed)
            return {k: observed[3][k] for k in ("volume", "index", "created")}
        except BaseException:
            self.close()
            raise
        finally:
            # On the second check retain only the original handles.
            if recheck:
                for handle in self.handles[base:]:
                    self.native.kernel.CloseHandle(handle)
                del self.handles[base:]

    def close(self) -> None:
        for handle in self.handles:
            self.native.kernel.CloseHandle(handle)
        self.handles.clear()
