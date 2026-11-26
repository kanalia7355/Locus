from __future__ import annotations

import builtins
import hashlib
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from app.connector_local import (
    MAX_DEPTH,
    MAX_ITEMS,
    REASON_DEPTH,
    REASON_ITEM_LIMIT,
    REASON_PATH_ESCAPE,
    REASON_ROOT_UNSET,
    REASON_SYMLINK,
    ROOT_ENV,
    LocalFolderConnector,
)
from app.service import Principal, Service


def make_root(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    root.mkdir()
    return root


def test_list_items_returns_metadata_without_reading_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_root(tmp_path)
    (root / "notes.txt").write_text("hello", encoding="utf-8")
    (root / "sub").mkdir()
    (root / "sub" / "report.md").write_text("# report", encoding="utf-8")
    (root / "image.png").write_bytes(b"\x89PNG")

    opened: list[str] = []
    real_open = builtins.open

    def tracking_open(file: Any, *args: Any, **kwargs: Any) -> Any:
        opened.append(str(file))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", tracking_open)
    connector = LocalFolderConnector(root=root, env={})
    items, cursor = connector.list_items()

    assert opened == []
    assert cursor is None
    assert [item.external_id for item in items] == [
        "image.png",
        "notes.txt",
        "sub/report.md",
    ]
    by_id = {item.external_id: item for item in items}
    assert by_id["notes.txt"].name == "notes.txt"
    assert by_id["notes.txt"].size == 5
    assert by_id["notes.txt"].modified_at > 0
    assert by_id["notes.txt"].content_hash == ""
    assert str(by_id["notes.txt"].size) in by_id["notes.txt"].revision

    raw = connector.fetch_content("notes.txt")
    assert raw == b"hello"
    assert len(opened) == 1
    assert Path(opened[0]).name == "notes.txt"


def test_source_selects_a_relative_subfolder(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    (root / "top.txt").write_text("top", encoding="utf-8")
    (root / "sub").mkdir()
    (root / "sub" / "inside.txt").write_text("inside", encoding="utf-8")

    connector = LocalFolderConnector("sub", root=root, env={})

    items, _ = connector.list_items()
    assert [item.external_id for item in items] == ["sub/inside.txt"]
    assert connector.fetch_content("sub/inside.txt") == b"inside"


def test_source_and_fetch_reject_path_escapes(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    (root / "inside.txt").write_text("inside", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    for source in (
        "../outside.txt",
        "sub/../../outside.txt",
        ".. ",
        "sub/.. ",
        str(outside),
        str(tmp_path),
    ):
        connector = LocalFolderConnector(source, root=root, env={})
        items, cursor = connector.list_items()
        assert items == []
        assert cursor is None
        assert any(rejection.reason == REASON_PATH_ESCAPE for rejection in connector.rejections)

    connector = LocalFolderConnector(root=root, env={})
    for external_id in (
        "../outside.txt",
        "sub/../../outside.txt",
        str(outside),
        "C:\\Windows\\win.ini",
        "\\\\evilhost\\share\\secret.txt",
        "inside.txt:stream",
        ".. ",
        "...",
        "notes.txt ",
        "sub/notes?.txt",
        "",
    ):
        with pytest.raises(KeyError):
            connector.fetch_content(external_id)
    assert any(rejection.reason == REASON_PATH_ESCAPE for rejection in connector.rejections)


def test_fetch_is_read_only(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    path = root / "notes.txt"
    path.write_text("keep me", encoding="utf-8")
    before = path.read_bytes()
    before_stat = path.stat()

    connector = LocalFolderConnector(root=root, env={})
    assert connector.fetch_content("notes.txt") == before

    after_stat = path.stat()
    assert path.read_bytes() == before
    assert after_stat.st_size == before_stat.st_size
    assert after_stat.st_mtime_ns == before_stat.st_mtime_ns
    assert [entry.name for entry in root.iterdir()] == ["notes.txt"]


def test_symlinked_file_outside_root_is_not_followed(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("secret", encoding="utf-8")
    link = root / "leak.txt"
    try:
        os.symlink(secret, link)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation not supported: {exc}")

    connector = LocalFolderConnector(root=root, env={})
    items, _ = connector.list_items()
    assert all(item.external_id != "leak.txt" for item in items)
    assert any(rejection.reason == REASON_SYMLINK for rejection in connector.rejections)
    with pytest.raises(KeyError):
        connector.fetch_content("leak.txt")


def test_fetch_rechecks_after_listing_when_file_is_replaced(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    path = root / "note.txt"
    path.write_text("inside", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    connector = LocalFolderConnector(root=root, env={})

    items, _ = connector.list_items()
    assert [item.external_id for item in items] == ["note.txt"]

    path.unlink()
    try:
        os.symlink(outside, path)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation not supported: {exc}")

    with pytest.raises(KeyError):
        connector.fetch_content("note.txt")
    assert any(rejection.reason == REASON_SYMLINK for rejection in connector.rejections)


def test_symlinked_directory_outside_root_is_not_traversed(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    link = root / "linked"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation not supported: {exc}")

    connector = LocalFolderConnector(root=root, env={})
    items, _ = connector.list_items()
    assert all("secret.txt" not in item.external_id for item in items)
    assert any(rejection.reason == REASON_SYMLINK for rejection in connector.rejections)
    with pytest.raises(KeyError):
        connector.fetch_content("linked/secret.txt")


def test_junction_outside_root_is_not_traversed(tmp_path: Path) -> None:
    if os.name != "nt":
        pytest.skip("junction creation is Windows-only")
    root = make_root(tmp_path)
    outside = tmp_path / "outside-junction"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    junction = root / "jn"
    result = subprocess.run(  # noqa: S603
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],  # noqa: S607
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0 or not junction.exists():
        pytest.skip(f"junction creation not supported: {result.stderr or result.stdout}")

    connector = LocalFolderConnector(root=root, env={})
    items, _ = connector.list_items()
    assert all(item.external_id != "jn/secret.txt" for item in items)
    assert any(rejection.reason == REASON_SYMLINK for rejection in connector.rejections)
    with pytest.raises(KeyError):
        connector.fetch_content("jn/secret.txt")


def test_connector_is_unavailable_without_a_root(tmp_path: Path) -> None:
    connector = LocalFolderConnector(env={})
    assert connector.configured is False

    items, cursor = connector.list_items()
    assert items == []
    assert cursor is None
    assert any(rejection.reason == REASON_ROOT_UNSET for rejection in connector.rejections)
    with pytest.raises(KeyError):
        connector.fetch_content("notes.txt")

    assert LocalFolderConnector(env={ROOT_ENV: "relative/folder"}).configured is False
    assert LocalFolderConnector(env={ROOT_ENV: "\\\\host\\share"}).configured is False


def test_root_comes_from_the_environment(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    (root / "env.txt").write_text("env", encoding="utf-8")

    connector = LocalFolderConnector(env={ROOT_ENV: str(root)})

    assert connector.configured is True
    items, _ = connector.list_items()
    assert [item.external_id for item in items] == ["env.txt"]


def test_enumeration_stops_at_the_depth_limit(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    current = root
    for index in range(MAX_DEPTH + 2):
        current = current / f"d{index}"
        current.mkdir()
        (current / f"level{index}.txt").write_text("x", encoding="utf-8")

    connector = LocalFolderConnector(root=root, env={})
    items, _ = connector.list_items()
    external_ids = {item.external_id for item in items}

    assert any(external_id.endswith("/level0.txt") for external_id in external_ids)
    assert any(external_id.endswith(f"/level{MAX_DEPTH - 1}.txt") for external_id in external_ids)
    assert not any(external_id.endswith(f"/level{MAX_DEPTH}.txt") for external_id in external_ids)
    assert any(rejection.reason == REASON_DEPTH for rejection in connector.rejections)


def test_enumeration_stops_at_the_item_limit(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    for index in range(MAX_ITEMS + 5):
        (root / f"f{index:04d}.txt").touch()

    connector = LocalFolderConnector(root=root, env={})
    items, _ = connector.list_items()

    assert len(items) == MAX_ITEMS
    assert all(item.external_id != f"f{MAX_ITEMS + 4:04d}.txt" for item in items)
    assert any(rejection.reason == REASON_ITEM_LIMIT for rejection in connector.rejections)


def test_sync_engine_registers_documents_from_the_folder(service: Service, tmp_path: Path) -> None:
    root = make_root(tmp_path)
    content = "hello from explorer"
    (root / "note.txt").write_text(content, encoding="utf-8")
    connector = LocalFolderConnector(root=root, env={})
    service.register_sync_connector("local_folder", connector, configured=connector.configured)

    with service.db() as db:
        row = db.execute("SELECT * FROM users WHERE username='admin'").fetchone()
    actor = Principal(row["id"], row["username"], bool(row["system_admin"]), False)

    result = service.sync_connector(actor, "local_folder", "project-a", "local-source")

    assert result["registered"] == 1
    assert result["failed"] == 0
    origin = service.get_document_origin("local_folder", "note.txt")
    assert origin is not None
    assert origin["content_hash"] == hashlib.sha256(content.encode("utf-8")).hexdigest()
    with service.db() as db:
        document = db.execute(
            "SELECT name,content FROM documents WHERE id=?", (origin["document_id"],)
        ).fetchone()
    assert document is not None
    assert document["name"] == "note.txt"
    assert document["content"] == content
