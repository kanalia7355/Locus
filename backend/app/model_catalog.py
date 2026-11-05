"""Explicit, metadata-only local model inventory. Never loads or imports models."""

import asyncio
import ctypes
import hashlib
import json
import os
import stat
import threading
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import HTTPException

HTTP_SECONDS = 2.0
MAX_BYTES = 1_048_576
MAX_MODELS = 100
MAX_ENTRIES = 2000
MAX_DEPTH = 5


def reparse(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def local_volume(path: Path) -> bool:
    if os.name != "nt":
        return True
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetDriveTypeW.argtypes = [ctypes.c_wchar_p]
    kernel.GetDriveTypeW.restype = ctypes.c_uint
    return kernel.GetDriveTypeW(path.anchor) in {2, 3, 5, 6}


def checked_directories(path: Path) -> None:
    # Inspect from the volume root down; checking a descendant first would already
    # traverse a junction ancestor. No resolve()/stat-following before this check.
    for directory in reversed((path, *path.parents)):
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or reparse(directory):
            raise ValueError("Linked or unavailable model directory")


def file_metadata(path: Path, approved: Path) -> os.stat_result:
    current = path
    for _ in range(8):
        current.relative_to(approved)
        checked_directories(current.parent)
        info = current.lstat()
        if not reparse(current):
            return info
        if stat.S_ISDIR(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x10:
            raise ValueError("Linked model directory")
        if not stat.S_ISLNK(info.st_mode):
            raise ValueError("Unsupported model reparse point")
        target = os.readlink(current)
        # Windows readlink may return a local extended-length substitute path.
        if target.startswith("\\\\?\\"):
            target = target[4:]
            if len(target) < 3 or target[1:3] != ":\\":
                raise ValueError("Nonlocal model link")
        if target.startswith(("\\\\", "//")):
            raise ValueError("Nonlocal model link")
        current = Path(os.path.abspath(current.parent / target))
        current.relative_to(approved)  # Pure lexical check, BEFORE target metadata access.
    raise ValueError("Model link chain too long")


class ModelCatalog:
    def __init__(
        self,
        roots: dict[str, Path] | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        # Construct suggestions only. No folder inspection or service request at startup.
        if roots is None:
            cache = os.getenv("HF_HUB_CACHE") or str(
                Path(os.getenv("HF_HOME", str(Path.home() / ".cache/huggingface"))) / "hub"
            )
            roots = {"hf-cache": Path(cache)}
            extra = json.loads(os.getenv("LOCUS_MODEL_ROOTS", "[]"))
            if not isinstance(extra, list) or len(extra) > 3:
                raise ValueError("Invalid local model folder configuration")
            for index, value in enumerate(extra, 1):
                if not isinstance(value, str) or len(value) > 4096:
                    raise ValueError("Invalid local model folder configuration")
                roots[f"folder-{index}"] = Path(value)
        if len(roots) > 4 or any(
            not path.is_absolute() or str(path).startswith(("\\\\", "//"))
            for path in roots.values()
        ):
            raise ValueError("Local model folders must be absolute local paths")
        self.roots = dict(roots)
        self.transport = transport
        self.lock = threading.Lock()

    def sources(self) -> list[dict[str, str]]:
        return [{"id": "ollama", "label": "Ollama 登録モデル", "kind": "ollama"}] + [
            {
                "id": key,
                "label": "Hugging Face 標準キャッシュ"
                if key == "hf-cache"
                else f"モデルフォルダー {index}",
                "kind": "folder",
            }
            for index, key in enumerate(self.roots, 1)
        ]

    @staticmethod
    def _record(
        source: str, identity: str, name: str, size: int, format_name: str, status: str
    ) -> dict[str, Any]:
        return {
            "id": hashlib.sha256((source + "\0" + identity).encode()).hexdigest()[:24],
            "source_id": source,
            "name": name[:200],
            "size_bytes": size,
            "format": format_name,
            "status": status,
            "inference_enabled": False,
        }

    async def _ollama(self, timeout: float) -> list[dict[str, Any]]:
        async with asyncio.timeout(timeout):
            async with httpx.AsyncClient(
                trust_env=False,
                follow_redirects=False,
                transport=self.transport,
                timeout=timeout,
            ) as client:
                async with client.stream(
                    "GET",
                    "http://127.0.0.1:11434/api/tags",
                    headers={"Accept": "application/json", "Accept-Encoding": "identity"},
                ) as response:
                    if (
                        response.status_code != 200
                        or response.headers.get("content-encoding", "identity") != "identity"
                    ):
                        raise ValueError("Local model inventory unavailable")
                    body = bytearray()
                    async for part in response.aiter_bytes():
                        if len(part) > MAX_BYTES - len(body):
                            raise ValueError("Local model inventory too large")
                        body.extend(part)
                    value = json.loads(body)
                    if not isinstance(value, dict) or not isinstance(value.get("models"), list):
                        raise ValueError("Invalid local model inventory")
                    return value["models"]  # type: ignore[no-any-return]

    def _files(
        self, source: str, root: Path, deadline: float
    ) -> tuple[list[dict[str, Any]], bool, int]:
        # Reject directory links, including junction ancestors, before enumeration.
        approved = Path(os.path.abspath(root))
        if not local_volume(approved):
            raise ValueError("Model folders require local storage")
        checked_directories(approved)
        stack = [(approved, 0)]
        models: dict[str, dict[str, Any]] = {}
        count, rejected, truncated = 0, 0, False
        while stack:
            directory, depth = stack.pop()
            with os.scandir(directory) as entries:
                for entry in entries:
                    count += 1
                    if count > MAX_ENTRIES or time.monotonic() >= deadline:
                        return list(models.values()), True, rejected
                    path = Path(entry.path)
                    try:
                        info = file_metadata(path, approved)
                        if stat.S_ISDIR(info.st_mode):
                            if reparse(path):
                                rejected += 1
                            elif depth < MAX_DEPTH:
                                stack.append((path, depth + 1))
                            else:
                                truncated = True
                            continue
                        if not stat.S_ISREG(info.st_mode) or any(
                            ord(char) < 32 for char in path.name
                        ):
                            continue
                        suffix = path.suffix.lower()
                        if suffix not in {".gguf", ".safetensors"}:
                            continue
                        relative = path.relative_to(approved)
                        identity = (
                            relative.as_posix() if suffix == ".gguf" else relative.parent.as_posix()
                        )
                        parts = relative.parts
                        name = path.name if suffix == ".gguf" else (path.parent.name or root.name)
                        if parts[0].startswith("models--"):
                            name = parts[0][8:].replace("--", "/")
                        if identity in models:
                            models[identity]["size_bytes"] += info.st_size
                        else:
                            models[identity] = self._record(
                                source,
                                identity,
                                name,
                                info.st_size,
                                "gguf" if suffix == ".gguf" else "safetensors",
                                "requires-import-validation",
                            )
                        if len(models) >= MAX_MODELS:
                            return list(models.values()), True, rejected
                    except (OSError, ValueError, RuntimeError):
                        rejected += 1
        return list(models.values()), truncated, rejected

    def discover(self, sources: list[str]) -> dict[str, Any]:
        selected = list(dict.fromkeys(sources))
        if not selected or not set(selected) <= {"ollama", *self.roots}:
            raise HTTPException(422, "検出する場所を選択してください")
        if not self.lock.acquire(blocking=False):
            raise HTTPException(409, "モデルの検出中です。完了後に更新してください")
        try:
            deadline = time.monotonic() + 3
            models: list[dict[str, Any]] = []
            results: list[dict[str, Any]] = []
            for source in selected:
                truncated, rejected = False, 0
                found: list[dict[str, Any]] = []
                status = "complete"
                try:
                    if time.monotonic() >= deadline:
                        status, truncated = "partial", True
                    elif source == "ollama":
                        values = asyncio.run(
                            self._ollama(min(HTTP_SECONDS, deadline - time.monotonic()))
                        )
                        truncated = len(values) > MAX_MODELS
                        for value in values[:MAX_MODELS]:
                            if not isinstance(value, dict):
                                rejected += 1
                                continue
                            name, size = value.get("name"), value.get("size")
                            if (
                                not isinstance(name, str)
                                or not 0 < len(name) <= 200
                                or any(ord(c) < 32 for c in name)
                                or type(size) is not int
                                or not 0 <= size <= 2**63 - 1
                            ):
                                rejected += 1
                                continue
                            found.append(
                                self._record(
                                    source,
                                    name,
                                    name,
                                    size,
                                    "ollama",
                                    "registered-requires-runtime-validation",
                                )
                            )
                    else:
                        found, truncated, rejected = self._files(
                            source, self.roots[source], deadline
                        )
                    if truncated or rejected:
                        status = "partial"
                except (
                    OSError,
                    ValueError,
                    RuntimeError,
                    TimeoutError,
                    httpx.HTTPError,
                    RecursionError,
                ):
                    status = "unavailable"
                room = MAX_MODELS - len(models)
                if len(found) > room:
                    status, truncated = "partial", True
                models.extend(found[:room])
                results.append(
                    {
                        "id": source,
                        "status": status,
                        "truncated": truncated,
                        "rejected_entries": rejected,
                        "count": min(len(found), room),
                    }
                )
            return {
                "sources": results,
                "models": sorted(models, key=lambda item: (item["source_id"], item["name"])),
                "inference_enabled": False,
            }
        finally:
            self.lock.release()
