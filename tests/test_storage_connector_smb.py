"""SMB (Windows shared folder) connector tests (DATA-008 / T-PH7-202).

All tests are offline: local temporary directories act as the share root and a
synthetic ACL provider is injected. No real share, domain, or credentials.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from app.connectors.smb import (
    REASON_ADS,
    REASON_OTHER_HOST,
    REASON_OUT_OF_SCOPE,
    REASON_PATH_ESCAPE,
    REASON_RESERVED_NAME,
    REASON_SYMLINK,
    REASON_UNMAPPED_USER,
    AclSnapshot,
    FileAcl,
    ShareAcl,
    SmbSourceConnector,
    effective_permission,
    map_locus_user,
    permission_hash_for_snapshot,
)
from app.scanner import CLEAN, ScanResult
from app.service import Principal, Service
from test_api import ORIGIN, client_for, login

SOURCE_ID = "smb-test"
OBJECT_ID = "notes/sample.txt"
CONTENT = (
    "【合成サンプル・実研究データではありません】\n"
    "成膜条件Aは処理温度180°C、処理時間30分。\n"
    "成膜条件Bは処理温度200°C、処理時間20分。\n"
)


class AcceptingScanner:
    def scan(self, content: str) -> ScanResult:
        return CLEAN


class SyntheticAclProvider:
    """Injected ACL seam: returns snapshots by object id, can raise or return unknown."""

    def __init__(self) -> None:
        self.snapshots: dict[str, AclSnapshot | None] = {}
        self.raise_for: set[str] = set()
        self.calls: list[str] = []

    def set(
        self, object_id: str, *, share: dict[str, bool | None], file: dict[str, bool | None]
    ) -> None:
        self.snapshots[object_id] = AclSnapshot(
            share=ShareAcl(decisions=dict(share)),
            file=FileAcl(decisions=dict(file)),
        )

    def set_unknown(self, object_id: str) -> None:
        self.snapshots[object_id] = None

    def set_raise(self, object_id: str) -> None:
        self.raise_for.add(object_id)

    def get_snapshot(self, source_id: str, object_id: str) -> AclSnapshot | None:
        self.calls.append(object_id)
        if object_id in self.raise_for:
            raise RuntimeError("acl provider unavailable")
        return self.snapshots.get(object_id)


def write_object(root: Path, rel: str, content: str = CONTENT, *, encoding: str = "utf-8") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if encoding == "utf-8":
        path.write_text(content, encoding="utf-8")
    else:
        path.write_bytes(content.encode(encoding))
    return path


def make_connector(
    tmp_path: Path,
    *,
    source_id: str = SOURCE_ID,
    acl: SyntheticAclProvider | None = None,
    user_mapping: dict[str, str] | None = None,
) -> tuple[SmbSourceConnector, SyntheticAclProvider, Path]:
    root = tmp_path / "share"
    root.mkdir(parents=True, exist_ok=True)
    provider = acl or SyntheticAclProvider()
    mapping = (
        user_mapping
        if user_mapping is not None
        else {"admin": "sid-admin", "bob": "sid-bob", "alice": "sid-alice"}
    )
    connector = SmbSourceConnector(
        source_id=source_id,
        root=root,
        acl_provider=provider,
        user_mapping=mapping,
    )
    return connector, provider, root


def make_service(tmp_path: Path, connector: SmbSourceConnector) -> Service:
    svc = Service(tmp_path / "svc.sqlite3", scanner=AcceptingScanner(), source_connector=connector)
    svc.provision("admin", "Temporary-password-01!", system_admin=True)
    svc.provision("alice", "Temporary-password-02!")
    svc.provision("bob", "Temporary-password-03!")
    svc.create_project("org-a", "project-a", "研究プロジェクト")
    svc.assign("admin", "project-a", "project_lead")
    svc.assign("alice", "project-a", "researcher")
    svc.assign("bob", "project-a", "viewer")
    return svc


def ingest_source(
    service: Service, actor: Principal, object_id: str = OBJECT_ID, *, name: str = "sample.txt"
) -> str:
    document = service.source_ingest(
        actor,
        SOURCE_ID,
        object_id,
        CONTENT,
        name,
        kind="shared",
        project="project-a",
    )
    return str(document["id"])


def document_status(service: Service, document: str) -> str:
    with service.db() as db:
        return str(db.execute("SELECT status FROM documents WHERE id=?", (document,)).fetchone()[0])


def chunk_count(service: Service, document: str) -> int:
    with service.db() as db:
        return int(
            db.execute("SELECT COUNT(*) FROM chunks WHERE document_id=?", (document,)).fetchone()[0]
        )


# --- Acceptance 1: simultaneous invisibility across all six paths -------------


def test_smb_revocation_hides_all_six_paths_simultaneously(tmp_path: Path) -> None:
    connector, acl, root = make_connector(tmp_path)
    write_object(root, OBJECT_ID, CONTENT)
    acl.set(
        OBJECT_ID,
        share={"sid-admin": True, "sid-bob": True, "sid-alice": True},
        file={"sid-admin": True, "sid-bob": True, "sid-alice": True},
    )

    service = make_service(tmp_path, connector)
    try:
        admin = client_for(service)
        login(admin, "admin", "01")
        actor = service.authenticate(admin.cookies.get("locus_session"))
        document = ingest_source(service, actor)
        assert service.process_next() is True
        assert document_status(service, document) == "ready"

        bob = client_for(service)
        login(bob, "bob", "03")
        service.authenticate(bob.cookies.get("locus_session"))

        # (a) listing
        listed = bob.get("/api/documents", params={"project_id": "project-a"})
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [document]
        # (a-owner) owner listing branch must also be gated.
        owner_listed = admin.get("/api/documents", params={"project_id": "project-a"})
        assert [item["id"] for item in owner_listed.json()] == [document]
        # (b) document body and chunks
        assert bob.get(f"/api/documents/{document}").status_code == 200
        chunks = bob.get(f"/api/documents/{document}/chunks")
        assert chunks.status_code == 200 and chunks.json()
        # (c) related documents
        assert bob.get(f"/api/documents/{document}/related").status_code == 200
        # (d) search candidates and (e) conversation citations
        conversation = bob.post(
            "/api/conversations", json={"project_id": "project-a"}, headers=ORIGIN
        ).json()["id"]
        asked = bob.post(
            f"/api/conversations/{conversation}/messages",
            json={"text": "成膜条件", "scope": "all", "attachment_ids": []},
            headers=ORIGIN,
        )
        assert asked.status_code == 200
        assert asked.json()["citations"]
        with service.db() as db:
            db.execute(
                "INSERT INTO generated_answers VALUES (?,?,?)",
                (asked.json()["id"], "合成回答", "fixture-model"),
            )
        history = bob.get(f"/api/conversations/{conversation}").json()["messages"][0]
        # (f) generated answer
        assert history["answer"] == "合成回答"
        assert history["citations"]

        # Revoke bob and admin (owner-listing branch) in the synthetic ACL provider.
        acl.set(
            OBJECT_ID,
            share={"sid-admin": False, "sid-bob": False, "sid-alice": True},
            file={"sid-admin": False, "sid-bob": False, "sid-alice": True},
        )
        assert service.source_cycle(SOURCE_ID) is True

        assert bob.get("/api/documents", params={"project_id": "project-a"}).json() == []
        assert admin.get("/api/documents", params={"project_id": "project-a"}).json() == []
        assert bob.get(f"/api/documents/{document}").status_code == 404
        assert bob.get(f"/api/documents/{document}/chunks").status_code == 404
        assert bob.get(f"/api/documents/{document}/related").status_code == 404
        asked_after = bob.post(
            f"/api/conversations/{conversation}/messages",
            json={"text": "成膜条件", "scope": "all", "attachment_ids": []},
            headers=ORIGIN,
        )
        assert asked_after.status_code == 200
        assert asked_after.json()["citations"] == []
        history_after = bob.get(f"/api/conversations/{conversation}").json()["messages"][0]
        assert history_after["citations"] == []
        assert history_after["answer"] is None
        assert history_after["answer_hidden"] is True
    finally:
        service.close()


# --- Acceptance 2: ACL hash comparison ----------------------------------------


def test_smb_acl_hash_stable_skips_and_unrelated_change_keeps_visibility(tmp_path: Path) -> None:
    connector, acl, root = make_connector(tmp_path)
    write_object(root, OBJECT_ID, CONTENT)
    # Include an unrelated identity to exercise "unrelated part changed".
    acl.set(
        OBJECT_ID,
        share={"sid-admin": True, "sid-bob": True, "sid-alice": True, "sid-other": True},
        file={"sid-admin": True, "sid-bob": True, "sid-alice": True, "sid-other": True},
    )
    service = make_service(tmp_path, connector)
    try:
        admin = client_for(service)
        login(admin, "admin", "01")
        actor = service.authenticate(admin.cookies.get("locus_session"))
        document = ingest_source(service, actor)
        assert service.process_next() is True
        assert document_status(service, document) == "ready"
        assert chunk_count(service, document) == 1

        # Stable ACL: cycle should not re-index.
        chunks_before = chunk_count(service, document)
        assert service.source_cycle(SOURCE_ID) is False
        assert chunk_count(service, document) == chunks_before

        # Change only an unrelated identity (not mapped to any Locus user).
        acl.set(
            OBJECT_ID,
            share={"sid-admin": True, "sid-bob": True, "sid-alice": True, "sid-other": False},
            file={"sid-admin": True, "sid-bob": True, "sid-alice": True, "sid-other": False},
        )
        # Firing is allowed; visibility for mapped users must not change.
        service.source_cycle(SOURCE_ID)
        assert document_status(service, document) == "ready"
        assert chunk_count(service, document) == 1
        listed = admin.get("/api/documents", params={"project_id": "project-a"})
        assert [item["id"] for item in listed.json()] == [document]
        bob = client_for(service)
        login(bob, "bob", "03")
        listed_bob = bob.get("/api/documents", params={"project_id": "project-a"})
        assert [item["id"] for item in listed_bob.json()] == [document]
    finally:
        service.close()


# --- Acceptance 3: effective permission is most restrictive -------------------


def test_effective_permission_most_restrictive_pure_function() -> None:
    # Share allow, file deny -> unreadable
    assert effective_permission(True, False) is False
    # Share deny, file allow -> unreadable
    assert effective_permission(False, True) is False
    # One side unobtainable -> unreadable (fail closed)
    assert effective_permission(True, None) is None
    assert effective_permission(None, True) is None
    assert effective_permission(None, None) is None
    assert effective_permission(False, None) is False
    assert effective_permission(None, False) is False
    # Both allow -> readable
    assert effective_permission(True, True) is True
    # Both deny -> unreadable
    assert effective_permission(False, False) is False


def test_smb_effective_permission_share_file_combinations(tmp_path: Path) -> None:
    connector, acl, root = make_connector(tmp_path)
    write_object(root, OBJECT_ID, CONTENT)

    # Share allow, file deny
    acl.set(OBJECT_ID, share={"sid-bob": True}, file={"sid-bob": False})
    assert connector.can_read(SOURCE_ID, OBJECT_ID, "bob") is False

    # Share deny, file allow
    acl.set(OBJECT_ID, share={"sid-bob": False}, file={"sid-bob": True})
    assert connector.can_read(SOURCE_ID, OBJECT_ID, "bob") is False

    # Share obtainable only (file unknown/missing)
    acl.set(OBJECT_ID, share={"sid-bob": True}, file={})
    assert connector.can_read(SOURCE_ID, OBJECT_ID, "bob") is not True

    # File obtainable only (share unknown/missing)
    acl.set(OBJECT_ID, share={}, file={"sid-bob": True})
    assert connector.can_read(SOURCE_ID, OBJECT_ID, "bob") is not True

    # Both allow
    acl.set(OBJECT_ID, share={"sid-bob": True}, file={"sid-bob": True})
    assert connector.can_read(SOURCE_ID, OBJECT_ID, "bob") is True


# --- Acceptance 4: path containment ------------------------------------------


def test_path_containment_rejects_parent_ref(tmp_path: Path) -> None:
    connector, acl, root = make_connector(tmp_path)
    write_object(root, "safe.txt", CONTENT)
    acl.set("safe.txt", share={"sid-admin": True}, file={"sid-admin": True})
    connector.rejections.clear()
    objects = connector.list_objects(SOURCE_ID)
    assert [o.object_id for o in objects] == ["safe.txt"]
    # Direct access attempt with ..
    bad = "../escape.txt"
    connector.rejections.clear()
    assert connector.can_read(SOURCE_ID, bad, "admin") is not True
    assert connector.permission_hash(SOURCE_ID, bad) is None
    assert any(r.reason == REASON_PATH_ESCAPE for r in connector.rejections)
    connector.rejections.clear()
    with pytest.raises(KeyError):
        connector.read_object(SOURCE_ID, bad)
    assert any(r.reason == REASON_PATH_ESCAPE for r in connector.rejections)


def test_path_containment_rejects_symlink_outside_root(tmp_path: Path) -> None:
    connector, acl, root = make_connector(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text(CONTENT, encoding="utf-8")
    link = root / "leak.txt"
    try:
        os.symlink(secret, link)
    except (OSError, NotImplementedError) as e:
        pytest.skip(f"symlink creation not supported: {e}")
    acl.set("leak.txt", share={"sid-admin": True}, file={"sid-admin": True})
    connector.rejections.clear()
    objects = connector.list_objects(SOURCE_ID)
    assert all(o.object_id != "leak.txt" for o in objects)
    assert any(r.reason == REASON_SYMLINK for r in connector.rejections)
    assert connector.can_read(SOURCE_ID, "leak.txt", "admin") is not True


def test_path_containment_rejects_junction_outside_root(tmp_path: Path) -> None:
    connector, acl, root = make_connector(tmp_path)
    outside = tmp_path / "outside-junction"
    outside.mkdir()
    (outside / "secret.txt").write_text(CONTENT, encoding="utf-8")
    junction = root / "jn"
    # Junction creation on Windows: mklink /J
    import subprocess

    result = subprocess.run(  # noqa: S603
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],  # noqa: S607
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0 or not junction.exists():
        pytest.skip(f"junction creation not supported: {result.stderr or result.stdout}")
    acl.set("jn/secret.txt", share={"sid-admin": True}, file={"sid-admin": True})
    connector.rejections.clear()
    objects = connector.list_objects(SOURCE_ID)
    assert all("secret.txt" not in o.object_id or o.object_id != "jn/secret.txt" for o in objects)
    assert any(r.reason == REASON_SYMLINK for r in connector.rejections)
    assert connector.can_read(SOURCE_ID, "jn/secret.txt", "admin") is not True


def test_path_containment_rejects_other_host_unc(tmp_path: Path) -> None:
    connector, acl, root = make_connector(tmp_path)
    bad = "\\\\evilhost\\share\\secret.txt"
    connector.rejections.clear()
    assert connector.can_read(SOURCE_ID, bad, "admin") is not True
    assert connector.permission_hash(SOURCE_ID, bad) is None
    assert any(r.reason == REASON_OTHER_HOST for r in connector.rejections)
    connector.rejections.clear()
    with pytest.raises(KeyError):
        connector.read_object(SOURCE_ID, bad)
    assert any(r.reason == REASON_OTHER_HOST for r in connector.rejections)


def test_path_containment_rejects_windows_reserved_name(tmp_path: Path) -> None:
    connector, acl, root = make_connector(tmp_path)
    for bad in ["CON", "NUL.txt", "com1", "LPT9.csv", "AUX.md"]:
        connector.rejections.clear()
        assert connector.can_read(SOURCE_ID, bad, "admin") is not True
        assert connector.permission_hash(SOURCE_ID, bad) is None
        assert any(r.reason == REASON_RESERVED_NAME for r in connector.rejections), (
            bad,
            connector.rejections,
        )
        connector.rejections.clear()
        with pytest.raises(KeyError):
            connector.read_object(SOURCE_ID, bad)
        assert any(r.reason == REASON_RESERVED_NAME for r in connector.rejections), (
            bad,
            connector.rejections,
        )


def test_path_containment_rejects_alternate_data_stream(tmp_path: Path) -> None:
    connector, acl, root = make_connector(tmp_path)
    bad = "notes/file.txt:secret"
    connector.rejections.clear()
    assert connector.can_read(SOURCE_ID, bad, "admin") is not True
    assert connector.permission_hash(SOURCE_ID, bad) is None
    assert any(r.reason == REASON_ADS for r in connector.rejections)
    connector.rejections.clear()
    with pytest.raises(KeyError):
        connector.read_object(SOURCE_ID, bad)
    assert any(r.reason == REASON_ADS for r in connector.rejections)


# --- Acceptance 5: move/rename identity and no permission loosening -----------


def test_smb_move_rename_identity_and_no_permission_loosening(tmp_path: Path) -> None:
    connector, acl, root = make_connector(tmp_path)
    old_id = "notes/old.txt"
    new_id = "notes/new.txt"
    write_object(root, old_id, CONTENT)
    acl.set(
        old_id,
        share={"sid-admin": True, "sid-bob": True},
        file={"sid-admin": True, "sid-bob": True},
    )

    service = make_service(tmp_path, connector)
    try:
        admin = client_for(service)
        login(admin, "admin", "01")
        actor = service.authenticate(admin.cookies.get("locus_session"))
        document = ingest_source(service, actor, old_id, name="old.txt")
        assert service.process_next() is True
        assert document_status(service, document) == "ready"

        bob = client_for(service)
        login(bob, "bob", "03")
        assert [
            i["id"] for i in bob.get("/api/documents", params={"project_id": "project-a"}).json()
        ] == [document]

        # Revoke bob before move.
        acl.set(
            old_id,
            share={"sid-admin": True, "sid-bob": False},
            file={"sid-admin": True, "sid-bob": False},
        )
        assert service.source_cycle(SOURCE_ID) is True
        assert bob.get("/api/documents", params={"project_id": "project-a"}).json() == []

        # Move/rename on disk: old disappears, new appears.
        (root / old_id).rename(root / new_id)
        # New location: bob still not readable (no permission loosening on move).
        acl.set(
            new_id,
            share={"sid-admin": True, "sid-bob": False},
            file={"sid-admin": True, "sid-bob": False},
        )
        # Old location no longer exists as an object.
        acl.set_unknown(old_id)

        objects = connector.list_objects(SOURCE_ID)
        ids = [o.object_id for o in objects]
        assert old_id not in ids
        assert new_id in ids

        # Cycle after move: old bound document must remain invisible to bob.
        service.source_cycle(SOURCE_ID)
        assert bob.get("/api/documents", params={"project_id": "project-a"}).json() == []
        assert bob.get(f"/api/documents/{document}").status_code == 404
        # Even if someone asks for the new object directly through the connector,
        # bob cannot read it.
        assert connector.can_read(SOURCE_ID, new_id, "bob") is False
    finally:
        service.close()


# --- Acceptance 6: undecidable / unreachable -> fail closed, no 500 ----------


def test_smb_acl_provider_exception_fails_closed_no_500(tmp_path: Path) -> None:
    connector, acl, root = make_connector(tmp_path)
    write_object(root, OBJECT_ID, CONTENT)
    acl.set(
        OBJECT_ID,
        share={"sid-admin": True, "sid-bob": True},
        file={"sid-admin": True, "sid-bob": True},
    )
    service = make_service(tmp_path, connector)
    try:
        admin = client_for(service)
        login(admin, "admin", "01")
        actor = service.authenticate(admin.cookies.get("locus_session"))
        document = ingest_source(service, actor)
        assert service.process_next() is True
        assert document_status(service, document) == "ready"

        bob = client_for(service)
        login(bob, "bob", "03")
        assert bob.get(f"/api/documents/{document}").status_code == 200

        acl.set_raise(OBJECT_ID)
        service.source_cycle(SOURCE_ID)

        assert bob.get(f"/api/documents/{document}").status_code == 404
        assert bob.get(f"/api/documents/{document}/chunks").status_code == 404
        # No 500 leaked through the API paths.
        listed = bob.get("/api/documents", params={"project_id": "project-a"})
        assert listed.status_code == 200
        assert listed.json() == []
    finally:
        service.close()


def test_smb_acl_provider_unknown_fails_closed(tmp_path: Path) -> None:
    connector, acl, root = make_connector(tmp_path)
    write_object(root, OBJECT_ID, CONTENT)
    acl.set(
        OBJECT_ID,
        share={"sid-admin": True, "sid-bob": True},
        file={"sid-admin": True, "sid-bob": True},
    )
    service = make_service(tmp_path, connector)
    try:
        admin = client_for(service)
        login(admin, "admin", "01")
        actor = service.authenticate(admin.cookies.get("locus_session"))
        document = ingest_source(service, actor)
        assert service.process_next() is True

        bob = client_for(service)
        login(bob, "bob", "03")
        acl.set_unknown(OBJECT_ID)
        service.source_cycle(SOURCE_ID)

        assert bob.get(f"/api/documents/{document}").status_code == 404
        listed = bob.get("/api/documents", params={"project_id": "project-a"})
        assert listed.status_code == 200
        assert listed.json() == []
    finally:
        service.close()


def test_smb_share_unreachable_fails_closed(tmp_path: Path) -> None:
    connector, acl, root = make_connector(tmp_path)
    write_object(root, OBJECT_ID, CONTENT)
    acl.set(
        OBJECT_ID,
        share={"sid-admin": True, "sid-bob": True},
        file={"sid-admin": True, "sid-bob": True},
    )
    service = make_service(tmp_path, connector)
    try:
        admin = client_for(service)
        login(admin, "admin", "01")
        actor = service.authenticate(admin.cookies.get("locus_session"))
        document = ingest_source(service, actor)
        assert service.process_next() is True

        bob = client_for(service)
        login(bob, "bob", "03")

        # Share unreachable: remove the root.
        for p in sorted(root.rglob("*"), reverse=True):
            if p.is_file():
                p.unlink()
            elif p.is_dir():
                p.rmdir()
        root.rmdir()

        # ACL provider also cannot decide because share is gone.
        acl.set_unknown(OBJECT_ID)
        service.source_cycle(SOURCE_ID)

        assert bob.get(f"/api/documents/{document}").status_code == 404
        listed = bob.get("/api/documents", params={"project_id": "project-a"})
        assert listed.status_code == 200
        assert listed.json() == []
    finally:
        service.close()


# --- Acceptance 7: supported formats only, out-of-scope observable ----------


def test_smb_unsupported_format_size_and_encoding_are_out_of_scope(tmp_path: Path) -> None:
    connector, acl, root = make_connector(tmp_path)
    # Supported file - should be listed.
    write_object(root, "ok.txt", CONTENT)
    acl.set("ok.txt", share={"sid-admin": True}, file={"sid-admin": True})

    # Unsupported extension
    (root / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    acl.set("image.png", share={"sid-admin": True}, file={"sid-admin": True})

    # Too large (>256 KiB)
    big = "a" * (256 * 1024 + 1)
    write_object(root, "big.txt", big)
    acl.set("big.txt", share={"sid-admin": True}, file={"sid-admin": True})

    # Non-UTF-8
    (root / "latin1.txt").write_bytes("café".encode("latin-1"))
    acl.set("latin1.txt", share={"sid-admin": True}, file={"sid-admin": True})

    objects = connector.list_objects(SOURCE_ID)
    ids = [o.object_id for o in objects]
    assert ids == ["ok.txt"]

    reasons = {(r.object_id, r.reason) for r in connector.rejections}
    assert ("image.png", REASON_OUT_OF_SCOPE) in reasons
    assert ("big.txt", REASON_OUT_OF_SCOPE) in reasons
    assert ("latin1.txt", REASON_OUT_OF_SCOPE) in reasons

    # Not silently skipped: observable in rejections.
    out_of_scope_ids = {
        r.object_id for r in connector.rejections if r.reason == REASON_OUT_OF_SCOPE
    }
    assert {"image.png", "big.txt", "latin1.txt"}.issubset(out_of_scope_ids)


# --- Acceptance 8: user mapping is explicit, no similar-name grant ----------


def test_user_mapping_is_explicit_pure_function() -> None:
    mapping = {"alice": "CORP\\alice", "bob": "CORP\\bob"}
    assert map_locus_user("alice", mapping) == "CORP\\alice"
    assert map_locus_user("bob", mapping) == "CORP\\bob"
    # Similar names do not match.
    assert map_locus_user("Alice", mapping) is None
    assert map_locus_user("alice1", mapping) is None
    assert map_locus_user("alic", mapping) is None
    assert map_locus_user("bob ", mapping) is None
    assert map_locus_user("", mapping) is None


def test_smb_unmapped_user_sees_nothing(tmp_path: Path) -> None:
    connector, acl, root = make_connector(
        tmp_path,
        user_mapping={"admin": "sid-admin", "alice": "sid-alice"},  # bob unmapped
    )
    write_object(root, OBJECT_ID, CONTENT)
    acl.set(
        OBJECT_ID,
        share={"sid-admin": True, "sid-bob": True},
        file={"sid-admin": True, "sid-bob": True},
    )

    # Even if the ACL has a sid-bob identity, Locus user bob is not mapped -> no access.
    assert connector.can_read(SOURCE_ID, OBJECT_ID, "bob") is False
    assert any(r.reason == REASON_UNMAPPED_USER for r in connector.rejections)

    service = make_service(tmp_path, connector)
    try:
        admin = client_for(service)
        login(admin, "admin", "01")
        actor = service.authenticate(admin.cookies.get("locus_session"))
        document = ingest_source(service, actor)
        assert service.process_next() is True
        assert document_status(service, document) == "ready"

        bob = client_for(service)
        login(bob, "bob", "03")
        assert bob.get("/api/documents", params={"project_id": "project-a"}).json() == []
        assert bob.get(f"/api/documents/{document}").status_code == 404
    finally:
        service.close()


# --- Pure function: ACL hash -------------------------------------------------


def test_permission_hash_is_pure_and_stable() -> None:
    snap_a = AclSnapshot(share=ShareAcl({"sid": True}), file=FileAcl({"sid": True}))
    snap_b = AclSnapshot(share=ShareAcl({"sid": True}), file=FileAcl({"sid": True}))
    snap_c = AclSnapshot(share=ShareAcl({"sid": True}), file=FileAcl({"sid": False}))
    assert permission_hash_for_snapshot(snap_a) == permission_hash_for_snapshot(snap_b)
    assert permission_hash_for_snapshot(snap_a) != permission_hash_for_snapshot(snap_c)
    # Dict order must not matter.
    snap_d = AclSnapshot(share=ShareAcl({"b": True, "a": False}), file=FileAcl({"x": True}))
    snap_e = AclSnapshot(share=ShareAcl({"a": False, "b": True}), file=FileAcl({"x": True}))
    assert permission_hash_for_snapshot(snap_d) == permission_hash_for_snapshot(snap_e)
