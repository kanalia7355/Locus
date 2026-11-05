"""Only synthetic model metadata and mocked Ollama; no weights, login or inference."""

import asyncio
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from app.main import create_app
from app.model_catalog import ModelCatalog
from app.service import Service
from fastapi import HTTPException
from fastapi.testclient import TestClient
from test_api import ORIGIN, login


def client(service: Service, catalog: ModelCatalog) -> TestClient:
    return TestClient(
        create_app(service=service, start_worker=False, model_catalog=catalog),
        base_url="http://127.0.0.1",
        client=("127.0.0.1", 50000),
    )


def test_explicit_sources_and_system_admin_authorization(service: Service, tmp_path: Path) -> None:
    root = tmp_path / "models"
    root.mkdir()
    (root / "fixture.gguf").write_bytes(b"synthetic-not-a-real-model")
    calls: list[httpx.Request] = []

    def ollama(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"models": [{"name": "local-fixture:latest", "size": 123}]})

    catalog = ModelCatalog({"test-root": root}, transport=httpx.MockTransport(ollama))
    admin, member = client(service, catalog), client(service, catalog)
    request = {"sources": ["ollama", "test-root"]}
    assert admin.post("/api/admin/models/discover", headers=ORIGIN, json=request).status_code == 401
    login(member)
    assert member.get("/api/admin/models/sources").status_code == 403
    assert (
        member.post("/api/admin/models/discover", headers=ORIGIN, json=request).status_code == 403
    )
    login(admin, "admin", "01")
    sources = admin.get("/api/admin/models/sources")
    assert sources.status_code == 200 and calls == []
    assert str(root) not in sources.text
    result = admin.post("/api/admin/models/discover", headers=ORIGIN, json=request)
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["inference_enabled"] is False
    assert {item["name"] for item in data["models"]} == {"fixture.gguf", "local-fixture:latest"}
    assert all(not item["inference_enabled"] for item in data["models"])
    assert str(root) not in result.text
    assert len(calls) == 1 and str(calls[0].url) == "http://127.0.0.1:11434/api/tags"
    assert calls[0].method == "GET" and "authorization" not in calls[0].headers
    assert (
        admin.post(
            "/api/admin/models/discover", headers=ORIGIN, json={"sources": [str(root)]}
        ).status_code
        == 422
    )
    audit = admin.get("/api/admin/audit").text
    assert "model.discover" in audit
    assert "fixture.gguf" not in audit and str(root) not in audit


def test_hf_artifact_candidates_use_names_and_metadata_only(tmp_path: Path) -> None:
    root = tmp_path / "hub"
    model = root / "models--synthetic--example" / "snapshots" / "abc123"
    model.mkdir(parents=True)
    (model / "config.json").write_text("This is deliberately NOT parseable configuration")
    (model / "model-00001.safetensors").write_bytes(b"synthetic-a")
    (model / "model-00002.safetensors").write_bytes(b"synthetic-b")
    (model / "token").write_text("not-a-model")
    result = ModelCatalog({"hf-cache": root}).discover(["hf-cache"])
    assert len(result["models"]) == 1
    item = result["models"][0]
    assert item["name"] == "synthetic/example" and item["size_bytes"] == 22
    assert item["status"] == "requires-import-validation"
    assert "NOT parseable" not in json.dumps(result)


@pytest.mark.parametrize("kind", ["file", "directory"])
def test_links_cannot_escape_approved_model_root(tmp_path: Path, kind: str) -> None:
    root, outside = tmp_path / "models", tmp_path / "private"
    root.mkdir()
    outside.mkdir()
    (outside / "outside.gguf").write_text("not-readable-through-this-catalog")
    try:
        (root / "escape.gguf").symlink_to(outside / "outside.gguf") if kind == "file" else (
            root / "escape-dir"
        ).symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("This Windows user cannot create synthetic symlinks")
    result = ModelCatalog({"root": root}).discover(["root"])
    assert result["models"] == []
    assert result["sources"][0]["rejected_entries"] == 1
    assert str(outside) not in json.dumps(result)


def test_limits_and_busy_state_are_not_reported_as_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "models"
    root.mkdir()
    for index in range(4):
        (root / f"fixture-{index}.gguf").write_text("synthetic")
    monkeypatch.setattr("app.model_catalog.MAX_ENTRIES", 2)
    catalog = ModelCatalog({"root": root})
    result = catalog.discover(["root"])
    assert len(result["models"]) == 2
    assert result["sources"][0]["status"] == "partial" and result["sources"][0]["truncated"]
    with catalog.lock, pytest.raises(HTTPException) as busy:
        catalog.discover(["root"])
    assert busy.value.status_code == 409


@pytest.mark.skipif(sys.platform != "win32", reason="Windows junction fixture")
def test_windows_junction_cannot_expose_another_folder(tmp_path: Path) -> None:
    root, outside = tmp_path / "models", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "unapproved.gguf").write_text("synthetic")
    link = root / "junction"
    result = subprocess.run(  # noqa: S603 — fixed command and test-owned paths only
        [
            str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/cmd.exe"),
            "/d",
            "/c",
            "mklink",
            "/J",
            str(link),
            str(outside),
        ],
        capture_output=True,
        timeout=10,
        check=False,
    )
    if result.returncode:
        pytest.skip("Synthetic junction creation unavailable")
    try:
        result = ModelCatalog({"root": root}).discover(["root"])
        assert result["models"] == []
        assert result["sources"][0]["rejected_entries"] == 1
    finally:
        os.rmdir(link)  # Remove only the fixture junction, never recurse into its target.


def test_forced_rotation_cannot_activate_discovery(service: Service) -> None:
    calls = []
    catalog = ModelCatalog({}, transport=httpx.MockTransport(lambda request: calls.append(request)))
    admin = client(service, catalog)
    assert (
        admin.post(
            "/api/auth/login",
            headers=ORIGIN,
            json={"username": "admin", "password": "Temporary-password-01!"},
        ).status_code
        == 200
    )
    assert admin.get("/api/admin/models/sources").status_code == 403
    assert (
        admin.post(
            "/api/admin/models/discover", headers=ORIGIN, json={"sources": ["ollama"]}
        ).status_code
        == 403
    )
    assert calls == []


def test_admin_revocation_during_io_blocks_inventory_return(service: Service) -> None:
    def revoked(request: httpx.Request) -> httpx.Response:
        with service.db() as db:
            db.execute("UPDATE users SET system_admin=0 WHERE username='admin'")
        return httpx.Response(200, json={"models": [{"name": "private-model", "size": 1}]})

    admin = client(service, ModelCatalog({}, transport=httpx.MockTransport(revoked)))
    login(admin, "admin", "01")
    result = admin.post("/api/admin/models/discover", headers=ORIGIN, json={"sources": ["ollama"]})
    assert result.status_code == 403
    assert "private-model" not in result.text


@pytest.mark.parametrize(
    "status,body", [(302, b""), (200, b"not-json"), (200, b"{"), (200, b"x" * 1_048_577)]
)
def test_bad_ollama_responses_do_not_follow_or_disclose(status: int, body: bytes) -> None:
    calls: list[str] = []

    def response(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(
            status, content=body, headers={"Location": "https://unapproved.invalid"}
        )

    result = ModelCatalog({}, transport=httpx.MockTransport(response)).discover(["ollama"])
    assert result["models"] == [] and result["sources"][0]["status"] == "unavailable"
    assert calls == ["http://127.0.0.1:11434/api/tags"]
    assert "unapproved" not in json.dumps(result)


def test_ollama_timeout_is_total_and_never_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    async def delayed(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        await asyncio.sleep(1)
        return httpx.Response(200, json={"models": []})

    monkeypatch.setattr("app.model_catalog.HTTP_SECONDS", 0.01)
    result = ModelCatalog({}, transport=httpx.MockTransport(delayed)).discover(["ollama"])
    assert result["sources"][0]["status"] == "unavailable" and len(calls) == 1


def test_unc_file_link_is_rejected_before_target_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "models"
    root.mkdir()
    link = root / "escape.gguf"
    link.write_text("synthetic")
    original = Path.lstat

    def metadata(path: Path, *args: object, **kwargs: object) -> object:
        if str(path).startswith("\\\\"):
            raise AssertionError("UNC metadata must not be inspected")
        if path == link:
            return SimpleNamespace(st_mode=stat.S_IFLNK | 0o777, st_file_attributes=0x400)
        return original(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "lstat", metadata)
        patch.setattr(os, "readlink", lambda path: "\\\\unapproved.invalid\\share\\weights.gguf")
        patch.setattr(
            Path, "resolve", lambda *a, **kw: pytest.fail("No resolution before containment")
        )
        result = ModelCatalog({"root": root}).discover(["root"])
    assert result["models"] == [] and result["sources"][0]["rejected_entries"] == 1


def test_directory_reparse_ancestor_is_rejected_before_descendant_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = tmp_path / "junction"
    root = parent / "models"
    root.mkdir(parents=True)
    original = Path.lstat

    def metadata(path: Path, *args: object, **kwargs: object) -> object:
        if path == parent:
            return SimpleNamespace(st_mode=stat.S_IFDIR | 0o777, st_file_attributes=0x410)
        if path == root:
            raise AssertionError("Directory ancestor must be rejected first")
        return original(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "lstat", metadata)
        result = ModelCatalog({"root": root}).discover(["root"])
    assert result["models"] == [] and result["sources"][0]["status"] == "unavailable"


def test_nonlocal_volume_never_inspects_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with monkeypatch.context() as patch:
        patch.setattr("app.model_catalog.local_volume", lambda path: False)
        patch.setattr(
            Path, "lstat", lambda *a, **kw: pytest.fail("Nonlocal volume must not be inspected")
        )
        result = ModelCatalog({"root": tmp_path}).discover(["root"])
    assert result["models"] == [] and result["sources"][0]["status"] == "unavailable"


def test_contained_cache_file_link_uses_only_checked_local_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "models"
    blob = root / "blobs" / "data"
    blob.parent.mkdir(parents=True)
    blob.write_text("synthetic")
    link = root / "model.gguf"
    link.write_text("not-the-weights")
    original = Path.lstat

    def metadata(path: Path, *args: object, **kwargs: object) -> object:
        if path == link:
            return SimpleNamespace(st_mode=stat.S_IFLNK | 0o777, st_file_attributes=0x400)
        return original(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "lstat", metadata)
        patch.setattr(os, "readlink", lambda path: "blobs/data")
        result = ModelCatalog({"root": root}).discover(["root"])
    assert result["models"][0]["size_bytes"] == len("synthetic")
    assert result["sources"][0]["status"] == "complete"
