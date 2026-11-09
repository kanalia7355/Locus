"""Existing-file admission uses synthetic metadata, never credential contents."""

from pathlib import Path

import pytest

from loop_engine import auth_file_profile as auth
from loop_engine import c_min_runtime as runtime
from loop_engine.security import SafetyError, fingerprint
from loop_engine.state_store import StateStore

SID = "S-1-5-21-1000"
ACL = (SID, 4, [(SID, 0x1F01FF, 0)])


@pytest.fixture
def profile(tmp_path, monkeypatch):
    home = tmp_path / "operator" / ".codex"
    home.mkdir(parents=True)
    (home / "config.toml").write_text("", encoding="utf-8")
    # No auth file is created: all credential-file observations are synthetic.
    observed = {
        "identity": dict(volume=1, index=2, size=10, created=3, written=4, attributes=32, links=1),
        "security": ACL,
    }
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home.parent))
    monkeypatch.setattr(auth, "_metadata", lambda path: observed.copy())
    monkeypatch.setattr(runtime, "file_security", lambda path: ACL)
    monkeypatch.setattr(
        runtime, "Native", lambda: type("Owner", (), {"current_sid": lambda _: SID})()
    )
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setattr(runtime, "key_metadata", lambda *a, **k: pytest.fail("credential access"))
    original = Path.open

    def guarded(path, *args, **kwargs):
        assert path.name not in {"auth.json", "codex_auth.age"}
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)
    binding = auth.inspect_existing(home, SID)
    state = StateStore(tmp_path / "state.db")
    state.set_metadata(
        "c_min_auth_profile",
        dict(
            home=str(home), backend="existing-file", config_hash=fingerprint(""), sid=SID, **binding
        ),
    )
    return home, state, observed


def test_registered_file_uses_only_metadata(profile):
    home, state, _ = profile
    before = set(home.iterdir())
    runtime.verify_profile(state)
    assert set(home.iterdir()) == before
    assert not (home / "auth.json").exists()


@pytest.mark.parametrize("mode", ["auto", "keyring", "ephemeral"])
def test_ambiguous_or_other_store_rejected(profile, mode):
    home, state, _ = profile
    raw = f'cli_auth_credentials_store="{mode}"\n'
    (home / "config.toml").write_text(raw)
    value = state.metadata("c_min_auth_profile")
    value["config_hash"] = fingerprint(raw)
    state.set_metadata("c_min_auth_profile", value)
    with pytest.raises(SafetyError, match="profile differs"):
        runtime.verify_profile(state)


@pytest.mark.parametrize(
    "field", ["volume", "index", "size", "created", "written", "attributes", "links"]
)
def test_changed_identity_holds(profile, field):
    _, state, observed = profile
    observed["identity"] = {**observed["identity"], field: 999}
    with pytest.raises(SafetyError, match="changed"):
        runtime.verify_profile(state)


@pytest.mark.parametrize(
    "acl",
    [
        ("other", 4, [(SID, 1, 0)]),
        (SID, 0, [(SID, 1, 0)]),
        (SID, 4, []),
        (SID, 4, [("S-1-1-0", 1, 0), (SID, 1, 0)]),
        (SID, 4, [(SID, 1, 0x20)]),
        (SID, 4, [(SID, 1, 8)]),
    ],
)
def test_weak_acl_rejected(acl):
    with pytest.raises(SafetyError):
        auth.private_acl(acl, SID)


def test_replacement_during_inspection_holds(profile, monkeypatch):
    home, _, observed = profile
    calls = iter([observed, {**observed, "identity": {"index": 999}}])
    monkeypatch.setattr(auth, "_metadata", lambda _: next(calls))
    with pytest.raises(SafetyError, match="changed during"):
        auth.inspect_existing(home, SID)


def test_untrusted_ancestor_write_holds(profile, monkeypatch):
    home, _, _ = profile
    monkeypatch.setattr(
        runtime,
        "file_security",
        lambda path: (SID, 4, [("S-1-1-0", 0x40000000, 0)]) if path == home.parent else ACL,
    )
    with pytest.raises(SafetyError, match="ancestor"):
        auth.inspect_existing(home, SID)


def test_reparse_auth_rejected_before_metadata(profile, monkeypatch):
    home, _, _ = profile
    monkeypatch.setattr(auth, "reparse", lambda path: path.name == "auth.json")
    monkeypatch.setattr(auth, "_metadata", lambda _: pytest.fail("must reject before opening"))
    with pytest.raises(SafetyError, match="private operator"):
        auth.inspect_existing(home, SID)


def test_metadata_structure_has_windows_abi():
    import ctypes

    assert ctypes.sizeof(auth._Info) == 52


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="Win32 metadata API")
def test_real_native_synthetic_file_requests_no_data_access(tmp_path, monkeypatch):
    from loop_engine.windows_pipe import Native

    path = tmp_path / "synthetic-metadata-only.json"
    path.write_bytes(b"synthetic, not credentials")
    native = Native()
    actual_create = native.kernel.CreateFileW
    requests = []

    def metadata_open(name, access, share, security, disposition, flags, template):
        requests.append(access)
        assert access == 0x20080  # READ_CONTROL | FILE_READ_ATTRIBUTES only
        return actual_create(name, access, share, security, disposition, flags, template)

    native.kernel.CreateFileW = metadata_open
    native.kernel.ReadFile = lambda *args: pytest.fail("data read forbidden")
    monkeypatch.setattr(auth, "Native", lambda: native)
    first = auth._metadata(path)
    second = auth._metadata(path)
    assert first == second
    assert first["identity"]["size"] == 26
    assert requests == [0x20080, 0x20080]


@pytest.mark.parametrize(
    "failure",
    [
        "drive",
        "open",
        "type",
        "information",
        "directory",
        "reparse",
        "links",
        "empty",
        "large",
        "index",
        "final",
        "final_failure",
    ],
)
def test_native_metadata_negative_contracts(monkeypatch, failure):
    import ctypes
    from pathlib import PureWindowsPath
    from types import SimpleNamespace

    class Function:
        def __init__(self, call):
            self.call = call

        def __call__(self, *args):
            return self.call(*args)

    closed = []
    path = PureWindowsPath("C:/synthetic/auth.json")

    def info(handle, pointer):
        value = ctypes.cast(pointer, ctypes.POINTER(auth._Info)).contents
        value.attributes = {"directory": 0x10, "reparse": 0x400}.get(failure, 32)
        value.links = 2 if failure == "links" else 1
        value.size_low = {"empty": 0, "large": 65537}.get(failure, 10)
        value.index_low = 0 if failure == "index" else 1
        return failure != "information"

    def final(handle, buffer, size, flags):
        buffer.value = "wrong" if failure == "final" else "\\\\?\\" + str(path)
        return 0 if failure == "final_failure" else len(buffer.value)

    kernel = SimpleNamespace(
        GetDriveTypeW=Function(lambda _: 4 if failure == "drive" else 3),
        CreateFileW=Function(lambda *args: ctypes.c_void_p(-1).value if failure == "open" else 123),
        GetFileType=Function(lambda _: 3 if failure == "type" else 1),
        GetFileInformationByHandle=Function(info),
        GetFinalPathNameByHandleW=Function(final),
        CloseHandle=lambda handle: closed.append(handle),
    )
    monkeypatch.setattr(auth, "reparse", lambda _: False)
    monkeypatch.setattr(
        auth, "Native", lambda: SimpleNamespace(kernel=kernel, security=lambda *a, **k: ACL)
    )
    with pytest.raises(SafetyError):
        auth._metadata(path)
    assert closed == ([] if failure in {"drive", "open"} else [123])


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="Win32 security API")
def test_real_filesystem_security_kind_matches_metadata(tmp_path):
    path = tmp_path / "synthetic-only"
    path.write_bytes(b"noncredential")
    assert runtime.file_security(path) == auth._metadata(path)["security"]
    assert runtime.file_security(tmp_path)[0]
