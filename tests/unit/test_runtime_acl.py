"""Explicit read-only runtime policy; strict credential ACL is never expanded."""

import ctypes
import sys
import time
from pathlib import Path

import pytest

from loop_engine import auth_file_profile as auth
from loop_engine.runtime_acl import APPROVAL, RX, VERSION, RuntimeAcl
from loop_engine.security import SafetyError, fingerprint

OWNER = "S-1-5-21-10-20-30-1001"
GROUP = "S-1-5-21-1-2-3-9999"
POLICY = {"version": VERSION, "approval": APPROVAL, "group_sid": GROUP}


def test_only_explicit_approved_policy_accepts_noninheriting_runtime_read():
    home = Path("synthetic-runtime").absolute()
    base = (OWNER, 0x1004, [(OWNER, 0x1F01FF, 3), (GROUP, RX, 0)])
    readonly = RuntimeAcl(home, OWNER, POLICY)
    readonly.validate(home, True, base)
    with pytest.raises(SafetyError):
        auth.private_acl(base, OWNER)
    for name, directory in [
        ("tmp", True),
        ("tmp/arg0-windows", True),
        ("tmp/arg0-windows/codex-arg0ABC123", True),
        ("tmp/arg0-windows/codex-arg0ABC123/apply_patch.bat", False),
    ]:
        readonly.validate(home / name, directory, base)


@pytest.mark.parametrize("change", ["missing", "version", "approval", "extra", "sid", "owner"])
def test_policy_is_not_an_implicit_exception(change):
    value = dict(POLICY)
    if change == "missing":
        value.pop("approval")
    elif change == "extra":
        value["wildcard"] = True
    elif change == "sid":
        value["group_sid"] = "S-1-1-0"
    elif change == "owner":
        value["group_sid"] = OWNER
    else:
        value[change] = "unapproved"
    with pytest.raises(SafetyError):
        RuntimeAcl(Path("synthetic").absolute(), OWNER, value)


@pytest.mark.parametrize(
    "change",
    [
        "write",
        "delete",
        "dac",
        "owner_right",
        "generic",
        "sid",
        "flag",
        "inherit",
        "inherit_only",
        "duplicate",
        "owner",
        "null",
        "unprotected",
    ],
)
def test_runtime_privilege_or_inheritance_changes_are_rejected(change):
    home = Path("synthetic").absolute()
    security = [OWNER, 0x1004, [(OWNER, 0x1F01FF, 3), (GROUP, RX, 0)]]
    masks = {
        "write": 2,
        "delete": 0x10000,
        "dac": 0x40000,
        "owner_right": 0x80000,
        "generic": 0x10000000,
    }
    if change in masks:
        security[2][-1] = (GROUP, RX | masks[change], 0)
    elif change == "sid":
        security[2].append(("S-1-1-0", 1, 0))
    elif change in {"flag", "inherit", "inherit_only"}:
        security[2][-1] = (GROUP, RX, {"flag": 32, "inherit": 3, "inherit_only": 8}[change])
    elif change == "duplicate":
        security[2].append((GROUP, RX, 0))
    elif change == "owner":
        security[0] = "other"
    elif change == "null":
        security[1] = 0
    else:
        security[1] = 4
    with pytest.raises(SafetyError):
        RuntimeAcl(home, OWNER, POLICY).validate(home, True, tuple(security))


@pytest.mark.parametrize(
    "path,directory",
    [
        ("auth.json", False),
        ("config.toml", False),
        ("skills/x", False),
        ("tmp/other", True),
        # Exact synthetic rejected-path canary, not a credential.
        # pragma: allowlist nextline secret
        ("tmp/arg0-windows/codex-arg0ABC123/unknown", False),
    ],
)
def test_runtime_checker_cannot_authorize_credentials_or_arbitrary_paths(path, directory):
    home = Path("synthetic").absolute()
    with pytest.raises(SafetyError):
        RuntimeAcl(home, OWNER, POLICY).validate(
            home / path, directory, (OWNER, 0x1004, [(OWNER, 1, 0), (GROUP, RX, 0)])
        )


def native_fixture():
    from test_acl_rehearsal import FixtureAcl

    f = FixtureAcl()
    f.readonly_runtime_candidate()
    expected = {
        "lease_approval": auth.LEASE_APPROVAL,
        "file_identity": auth._metadata(f.home / "auth.json")["identity"],
        "protection": {
            label: fingerprint(f.security(path))
            for label, path in [
                ("home", f.home),
                ("auth_file", f.home / "auth.json"),
                ("config", f.home / "config.toml"),
            ]
        },
    }
    return f, expected, RuntimeAcl(f.home, f.owner, POLICY)


@pytest.mark.parametrize("digest", [None, "", "unapproved"])
def test_legacy_profile_cannot_acquire_new_capability(monkeypatch, digest):
    monkeypatch.setattr(auth, "Native", lambda: pytest.fail("opened before approval"))
    with pytest.raises(SafetyError, match="capability approval"):
        auth.CredentialLease(Path("synthetic"), OWNER, {"lease_approval": digest})


@pytest.mark.skipif(sys.platform != "win32", reason="Real Win32 negative capabilities")
def test_all_five_handles_deny_content_and_mutation_capabilities():
    from ctypes import wintypes as w

    f, expected, runtime = native_fixture()
    lease = auth.CredentialLease(f.home, f.owner, expected, runtime)
    k = lease.native.kernel
    k.ReadFile.argtypes = [
        w.HANDLE,
        ctypes.c_void_p,
        w.DWORD,
        ctypes.POINTER(w.DWORD),
        ctypes.c_void_p,
    ]
    k.ReadFile.restype = w.BOOL
    k.WriteFile.argtypes = k.ReadFile.argtypes
    k.WriteFile.restype = w.BOOL
    buffer, count = ctypes.create_string_buffer(1), w.DWORD()
    try:
        for path, handle, _directory, _ in lease.held:
            assert not k.ReadFile(handle, buffer, 1, ctypes.byref(count), None)
            assert k.GetLastError() == 5
            assert not k.WriteFile(handle, buffer, 1, ctypes.byref(count), None)
            assert k.GetLastError() == 5
            with pytest.raises(OSError):
                path.rename(path.with_name(path.name + "-replacement"))
        lease.check()
    finally:
        lease.close()


@pytest.mark.skipif(sys.platform != "win32", reason="Real Win32 synthetic auth update")
def test_inplace_update_preserves_id_and_private_acl_but_holds_admission():
    f, expected, runtime = native_fixture()
    lease = auth.CredentialLease(f.home, f.owner, expected, runtime)
    target = f.home / "auth.json"
    try:
        # Pinned CLI FileAuthStorage save: create/write/truncate, not replacement.
        # Synthetic contents only. Compatibility never authorizes a real refresh.
        with target.open("wb") as writer:
            writer.write(b"SYNTHETIC_REFRESHED_NOT_A_CREDENTIAL")
        changed = auth._metadata(target)
        assert changed["identity"]["index"] == expected["file_identity"]["index"]
        auth.private_acl(changed["security"], f.owner)
        with pytest.raises(SafetyError):
            lease.check()
        with pytest.raises(SafetyError):
            lease.check()
    finally:
        lease.close()


@pytest.mark.skipif(sys.platform != "win32", reason="Real Win32 runtime compatibility")
def test_fresh_path_shims_remain_group_readable_with_full_credential_lease():
    from loop_engine.trial_arg0 import Arg0Guard

    f, expected, runtime = native_fixture()
    lease = auth.CredentialLease(f.home, f.owner, expected, runtime)
    guard = Arg0Guard(f.home, f.owner, runtime_acl=POLICY)
    try:
        fresh = f.home / "tmp/arg0-windows/codex-arg0XYZ123"
        fresh.mkdir()
        f.assign_fixture_owner(fresh)
        for name in (".lock", "apply_patch.bat", "applypatch.bat"):
            path = fresh / name
            path.write_bytes(b"SYNTHETIC_NOT_A_CREDENTIAL")
            f.assign_fixture_owner(path)
        observed = guard.check(str(fresh), time.time() - 2, time.time() + 2)
        assert observed["index"] != expected["file_identity"]["index"]
        assert f.can_read_as_synthetic_group(fresh / "apply_patch.bat")
        assert f.can_read_as_synthetic_group(fresh / "applypatch.bat")
        assert not f.can_read_as_synthetic_group(f.home / "auth.json")
        assert not f.can_read_as_synthetic_group(f.home / "config.toml")
        lease.check()
    finally:
        guard.close()
        lease.close()


@pytest.mark.skipif(sys.platform != "win32", reason="Real Win32 identity admission")
def test_recreated_credential_stays_private_and_old_identity_is_rejected():
    f, expected, runtime = native_fixture()
    target = f.home / "auth.json"
    target.rename(f.home / "old-synthetic-auth")
    target.write_bytes(b"SYNTHETIC_RECREATED_NOT_A_CREDENTIAL")
    f.assign_fixture_owner(target)
    assert not f.can_read_as_synthetic_group(target)
    auth.private_acl(f.security(target), f.owner)
    # Even restoring the exact approved protection cannot authorize a new ID.
    f.write(target, f.trusted(directory=False), owner=True)
    with pytest.raises(SafetyError, match="identity differs"):
        auth.CredentialLease(f.home, f.owner, expected, runtime)


@pytest.mark.skipif(sys.platform != "win32", reason="Real Win32 metadata lease")
def test_native_credential_lease_never_reads_data_and_blocks_replacement(monkeypatch):
    from loop_engine.windows_pipe import Native

    f, expected, runtime = native_fixture()
    native = Native()
    original = native.kernel.CreateFileW
    requests = []

    def metadata_only(name, access, share, *args):
        assert access == 0x200A0 and share == 3
        requests.append((str(name), access, share))
        return original(name, access, share, *args)

    native.kernel.CreateFileW = metadata_only
    native.kernel.ReadFile = lambda *a: pytest.fail("credential data read")
    monkeypatch.setattr(auth, "Native", lambda: native)
    lease = auth.CredentialLease(f.home, f.owner, expected, runtime)
    try:
        assert len(lease.held) == 5
        for name in ["auth.json", "config.toml"]:
            with pytest.raises(OSError):
                (f.home / name).rename(f.home / (name + ".replaced"))
        with pytest.raises(OSError):
            f.home.rename(f.root / "renamed-home")
        lease.check()
    finally:
        lease.close()
    assert lease.closed and len(requests) == 5


@pytest.mark.skipif(sys.platform != "win32", reason="Real Win32 metadata lease")
@pytest.mark.parametrize("change", ["acl", "data", "config", "home", "link"])
def test_native_lease_detects_change_and_never_recovers_silently(change):
    f, expected, runtime = native_fixture()
    lease = auth.CredentialLease(f.home, f.owner, expected, runtime)
    try:
        if change == "acl":
            f.write(f.home / "auth.json", f.trusted(directory=False) + f"(A;;0x1200a9;;;{GROUP})")
        elif change == "home":
            f.write(f.home, f.trusted() + f"(A;OICI;0x1200a9;;;{GROUP})", propagate=True)
        elif change == "link":
            # Probe fails closed if namespace checking cannot establish safety.
            lease.native.kernel.GetFinalPathNameByHandleW = lambda *a: 0
        else:
            (f.home / ("config.toml" if change == "config" else "auth.json")).write_bytes(
                b"changed synthetic input"
            )
        with pytest.raises(SafetyError):
            lease.check()
        with pytest.raises(SafetyError):
            lease.check()
    finally:
        lease.close()


@pytest.mark.skipif(sys.platform != "win32", reason="Real contained Windows CLI lifetime")
@pytest.mark.parametrize("mode", ["child", "cancel", "spawn", "crash", "timeout"])
def test_lease_outlives_settled_process_tree(mode):
    from loop_engine.process import ProcessRunner

    f, expected, runtime = native_fixture()
    lease = auth.CredentialLease(f.home, f.owner, expected, runtime)
    code = "import time;time.sleep(30)"
    if mode == "crash":
        code = "import os;os._exit(7)"
    if mode == "child":
        code = (
            "import subprocess,sys;subprocess.Popen([sys.executable,'-c',"
            "'import time;time.sleep(30)'],stdout=subprocess.DEVNULL,"
            "stderr=subprocess.DEVNULL);print('synthetic-parent-ended')"
        )
    argv = [str(f.root / "missing.exe")] if mode == "spawn" else [sys.executable, "-c", code]
    start = time.monotonic()
    lease.launch_started()
    result = ProcessRunner().run(
        argv,
        f.root,
        timeout=0.3 if mode == "timeout" else 3,
        require_settlement=True,
        before_resume=lambda *_: lease.check(),
        cancelled=lambda: mode == "cancel" and time.monotonic() - start > 0.2,
    )
    try:
        assert result.tree_settled is True
        if mode == "crash":
            assert result.outcome == "exit" and result.returncode == 7
        if mode == "timeout":
            assert result.outcome == "timeout"
        lease.process_finished(result.tree_settled)
        with pytest.raises(OSError):
            (f.home / "auth.json").rename(f.home / "moved")
    finally:
        if result.tree_settled is True:
            lease.close()


@pytest.mark.skipif(sys.platform != "win32", reason="Real Win32 metadata lease")
def test_unknown_process_lifetime_keeps_handles_and_blocks_another_lease(monkeypatch):
    f, expected, runtime = native_fixture()
    monkeypatch.setattr(auth, "_QUARANTINE", [])
    lease = auth.CredentialLease(f.home, f.owner, expected, runtime)
    lease.launch_started()  # No child is actually launched by this negative fixture.
    try:
        with pytest.raises(SafetyError):
            lease.process_finished(None)
        with pytest.raises(SafetyError):
            lease.close()
        assert auth._QUARANTINE == [lease] and lease.held
        with pytest.raises(OSError):
            (f.home / "auth.json").rename(f.home / "moved")
        with pytest.raises(SafetyError):
            auth.CredentialLease(f.home, f.owner, expected, runtime)
    finally:
        # Test-only cleanup: the fixture proves no process was launched. There
        # is intentionally no corresponding production reset API.
        lease.unsettled = False
        lease.close()
