"""Real NTFS, synthetic objects/SID only; never change the operator profile."""

import ctypes
import re
import sys
import time
from ctypes import wintypes as w
from pathlib import Path
from uuid import uuid4

import pytest

from loop_engine.auth_file_profile import private_acl
from loop_engine.c_min_runtime import file_security
from loop_engine.security import SafetyError, reparse
from loop_engine.trial_arg0 import Arg0Guard
from loop_engine.windows_pipe import Native

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Real Win32 ACL kernel required")
GROUP = "S-1-5-21-1-2-3-9999"  # A synthetic SID, never provision a user/group.


class FixtureAcl:
    def __init__(self):
        self.root = (
            Path(__file__).resolve().parents[2]
            / ".loop/runtime/probes"
            / ("acl-compat-" + uuid4().hex)
        )
        self.root.mkdir(parents=True)
        (self.root / "synthetic-only.marker").write_bytes(b"SYNTHETIC_ACL_ONLY")
        self.native = Native()
        self.owner = self.native.current_sid()
        a = self.native.advapi
        for name, result, args in [
            (
                "GetSecurityDescriptorDacl",
                w.BOOL,
                [
                    ctypes.c_void_p,
                    ctypes.POINTER(w.BOOL),
                    ctypes.POINTER(ctypes.c_void_p),
                    ctypes.POINTER(w.BOOL),
                ],
            ),
            (
                "GetSecurityDescriptorOwner",
                w.BOOL,
                [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(w.BOOL)],
            ),
            (
                "SetSecurityInfo",
                w.DWORD,
                [
                    w.HANDLE,
                    ctypes.c_int,
                    w.DWORD,
                    ctypes.c_void_p,
                    ctypes.c_void_p,
                    ctypes.c_void_p,
                    ctypes.c_void_p,
                ],
            ),
            ("ConvertStringSidToSidW", w.BOOL, [w.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]),
            (
                "CreateRestrictedToken",
                w.BOOL,
                [
                    w.HANDLE,
                    w.DWORD,
                    w.DWORD,
                    ctypes.c_void_p,
                    w.DWORD,
                    ctypes.c_void_p,
                    w.DWORD,
                    ctypes.c_void_p,
                    ctypes.POINTER(w.HANDLE),
                ],
            ),
            ("ImpersonateLoggedOnUser", w.BOOL, [w.HANDLE]),
        ]:
            function = getattr(a, name)
            function.restype, function.argtypes = result, args
        self.home = self.root / "profile"
        self.home.mkdir()
        self.write(self.home, self.trusted() + f"(A;OICI;0x1200a9;;;{GROUP})", owner=True)
        for relative in [
            "tmp/arg0-windows",
            ".sandbox-bin",
            ".sandbox",
            "skills",
            "plugins",
            "secrets",
        ]:
            (self.home / relative).mkdir(parents=True)
        for relative in [
            "auth.json",
            "config.toml",
            ".sandbox-bin/helper.txt",
            ".sandbox/state.txt",
            "skills/skill.txt",
            "plugins/plugin.txt",
            "tmp/arg0-windows/old-helper.txt",
            "secrets/synthetic.txt",
        ]:
            (self.home / relative).write_bytes(b"SYNTHETIC_NOT_A_CREDENTIAL")
        # Match public runtime's existing explicit helper read grant.
        self.write(
            self.home / ".sandbox-bin", self.trusted() + f"(A;OICI;0x1200a9;;;{GROUP})", owner=True
        )
        # A protected secret subtree must not be touched or queried by the repair.
        self.write(self.home / "secrets", self.trusted(), owner=True)
        self.targets = [
            self.home / x for x in ["auth.json", "config.toml", "tmp/arg0-windows", "tmp", "."]
        ]
        # Elevated runners default ownership to Administrators. Set exact fixture
        # owners before snapshots, never real profile owners.
        for path in self.targets:
            self.write(path, self.sddl(path), owner=True)
        self.before = {p: self.security(p) for p in self.home.rglob("*")}
        self.before[self.home] = self.security(self.home)
        self.identities = {p: (p.stat().st_dev, p.stat().st_ino) for p in self.targets}
        self.canaries = {p: p.read_bytes() for p in self.home.rglob("*") if p.is_file()}

    def guard(self, path):
        assert self.root.parent == Path(__file__).resolve().parents[2] / ".loop/runtime/probes"
        assert re.fullmatch(r"acl-compat-[a-f0-9]{32}", self.root.name)
        assert (self.root / "synthetic-only.marker").read_bytes() == b"SYNTHETIC_ACL_ONLY"
        assert path.resolve().is_relative_to(self.root.resolve())
        assert not any(reparse(p) for p in (path, *path.parents))

    def trusted(self, *, directory=True):
        flags = "OICI" if directory else ""
        return "D:P" + "".join(f"(A;{flags};FA;;;{sid})" for sid in [self.owner, "SY", "BA"])

    def security(self, path):
        self.guard(path)
        return file_security(path)

    def sddl(self, path):
        owner, control, entries = self.security(path)
        flags = ("P" if control & 0x1000 else "") + ("AI" if control & 0x400 else "")
        aces = []
        for sid, mask, bits in entries:
            ace_flags = "".join(
                name
                for flag, name in [(1, "OI"), (2, "CI"), (4, "NP"), (8, "IO"), (16, "ID")]
                if bits & flag
            )
            aces.append(f"(A;{ace_flags};0x{mask:x};;;{sid})")
        return "D:" + flags + "".join(aces)

    def write(self, path, sddl, *, owner=False, propagate=False):
        self.guard(path)
        descriptor, acl, owner_ptr = (ctypes.c_void_p() for _ in range(3))
        present, defaulted = w.BOOL(), w.BOOL()
        a, k = self.native.advapi, self.native.kernel
        assert a.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            "O:" + self.owner + sddl, 1, ctypes.byref(descriptor), None
        )
        handle = None
        try:
            assert (
                a.GetSecurityDescriptorDacl(
                    descriptor, ctypes.byref(present), ctypes.byref(acl), ctypes.byref(defaulted)
                )
                and present.value
                and acl.value
            )
            assert a.GetSecurityDescriptorOwner(
                descriptor, ctypes.byref(owner_ptr), ctypes.byref(defaulted)
            )
            # MAXIMUM_ALLOWED on DIRECTORY handles is the documented SetSecurityInfo
            # non-propagating path. File handles request metadata/WRITE_DAC only,
            # never FILE_READ_DATA. No returned handle escapes this fixture helper.
            access = 0x02000000 if path.is_dir() and not propagate else 0x60080
            if owner:
                access |= 0x80000
            handle = k.CreateFileW(str(path), access, 3, None, 3, 0x2200000, None)
            assert handle != ctypes.c_void_p(-1).value
            protected = sddl.startswith("D:P")
            info = 4 | (0x80000000 if protected else 0x20000000) | (1 if owner else 0)
            assert (
                a.SetSecurityInfo(handle, 1, info, owner_ptr if owner else None, None, acl, None)
                == 0
            )
        finally:
            if handle and handle != ctypes.c_void_p(-1).value:
                k.CloseHandle(handle)
            k.LocalFree(descriptor)

    def repair(self, *, fail_after=None):
        self.original_sddl = {p: self.sddl(p) for p in self.targets}
        self.after = {}
        for path in self.targets:
            assert self.security(path) == self.before[path]
            self.write(path, self.trusted(directory=path.is_dir()))
            self.after[path] = self.security(path)
            if len(self.after) == fail_after:
                raise SafetyError("Synthetic partial failure")

    def restore(self):
        # Validate ALL identities and after-states before the first rollback write.
        for p in self.targets:
            if (p.stat().st_dev, p.stat().st_ino) != self.identities[p] or self.security(
                p
            ) != self.after.get(p, self.before[p]):
                raise SafetyError("Synthetic recovery state differs")
        for p in reversed(self.targets):
            if p in self.after:
                self.write(p, self.original_sddl[p])

    def readonly_runtime_candidate(self):
        # Alternative ACL-only experiment; current runtime validators are NOT
        # changed to accept it. The group home ACE is explicitly NON-inheriting.
        self.targets = [self.home / "auth.json", self.home / "config.toml", self.home]
        self.original_sddl = {p: self.sddl(p) for p in self.targets}
        self.after = {}
        for p in self.targets:
            assert self.security(p) == self.before[p]
            desired = self.trusted(directory=p.is_dir())
            if p == self.home:
                desired += f"(A;;0x1200a9;;;{GROUP})"
            self.write(p, desired)
            self.after[p] = self.security(p)

    def can_read_as_synthetic_group(self, path, expected=b"SYNTHETIC_NOT_A_CREDENTIAL"):
        self.guard(path)
        a, k = self.native.advapi, self.native.kernel
        original, restricted = w.HANDLE(), w.HANDLE()
        pointer = ctypes.c_void_p()

        class SidAttributes(ctypes.Structure):
            _fields_ = [("sid", ctypes.c_void_p), ("attributes", w.DWORD)]

        assert a.OpenProcessToken(k.GetCurrentProcess(), 0xE, ctypes.byref(original))
        try:
            assert a.ConvertStringSidToSidW(GROUP, ctypes.byref(pointer))
            restriction = SidAttributes(pointer, 0)
            # Derive a process-local restricted token; no LogonUser, credentials,
            # real sandbox account, process launch or SAM operation is involved.
            assert a.CreateRestrictedToken(
                original,
                1,
                0,
                None,
                0,
                None,
                1,
                ctypes.byref(restriction),
                ctypes.byref(restricted),
            )
            assert a.ImpersonateLoggedOnUser(restricted)
            try:
                try:
                    with path.open("rb") as stream:
                        assert stream.read() == expected
                    return True
                except PermissionError:
                    return False
            finally:
                assert a.RevertToSelf()
        finally:
            if restricted:
                k.CloseHandle(restricted)
            k.CloseHandle(original)
            if pointer.value:
                k.LocalFree(pointer)


def test_nonpropagating_acl_repair_preserves_helpers_and_exact_rollback():
    f = FixtureAcl()
    assert f.can_read_as_synthetic_group(f.home / "auth.json")
    with pytest.raises(SafetyError):
        private_acl(f.security(f.home), f.owner)
    f.repair()
    for path in f.targets:
        private_acl(f.security(path), f.owner)
    # Existing Arg0Guard must accept private parent directories unchanged.
    guard = Arg0Guard(f.home, f.owner)
    fresh = f.home / "tmp/arg0-windows/codex-arg0ABC123"
    fresh.mkdir()
    for name in (".lock", "apply_patch.bat", "applypatch.bat"):
        (fresh / name).write_bytes(b"SYNTHETIC_NOT_A_CREDENTIAL")
    try:
        guard.check(str(fresh), time.time() - 2, time.time() + 2)
    finally:
        guard.close()
    assert not f.can_read_as_synthetic_group(fresh / "apply_patch.bat")
    new_skill = f.home / "skills/new-skill.txt"
    new_skill.write_bytes(b"SYNTHETIC_NOT_A_CREDENTIAL")
    assert f.can_read_as_synthetic_group(new_skill)
    assert not f.can_read_as_synthetic_group(f.home / "auth.json")
    for name in [
        ".sandbox-bin/helper.txt",
        ".sandbox/state.txt",
        "skills/skill.txt",
        "plugins/plugin.txt",
        "tmp/arg0-windows/old-helper.txt",
    ]:
        assert f.can_read_as_synthetic_group(f.home / name)
    for p, before in f.before.items():
        if p not in f.targets:
            assert f.security(p) == before
    assert f.canaries == {p: p.read_bytes() for p in f.canaries}
    f.restore()
    assert {p: f.security(p) for p in f.before} == f.before
    assert f.can_read_as_synthetic_group(f.home / "auth.json")
    with pytest.raises(SafetyError):
        private_acl(f.security(f.home), f.owner)


def test_default_propagation_breaks_inherited_helpers_and_regrant_is_detected():
    f = FixtureAcl()
    f.write(f.home, f.trusted(), propagate=True)
    assert not f.can_read_as_synthetic_group(f.home / "skills/skill.txt")
    # A separately protected synthetic auth file is not re-exposed by a later
    # official-style inheritable read grant, but home admission must HOLD.
    f.write(f.home / "auth.json", f.trusted(directory=False))
    f.write(f.home, f.trusted() + f"(A;OICI;0x1200a9;;;{GROUP})", propagate=True)
    assert not f.can_read_as_synthetic_group(f.home / "auth.json")
    with pytest.raises(SafetyError):
        private_acl(f.security(f.home), f.owner)


def test_recovery_refuses_acl_drift_and_changed_file_identity():
    f = FixtureAcl()
    f.repair()
    p = f.home / "config.toml"
    f.write(p, f.trusted(directory=False) + f"(A;;0x1200a9;;;{GROUP})")
    snapshot = {q: f.security(q) for q in f.before}
    with pytest.raises(SafetyError):
        f.restore()
    assert {q: f.security(q) for q in f.before} == snapshot
    f.write(p, f.trusted(directory=False))  # Synthetic out-of-band drift undone by the test only.
    assert f.security(p) == f.after[p]
    replacement = p.with_name("replacement")
    replacement.write_bytes(b"SYNTHETIC_NOT_A_CREDENTIAL")
    replacement.replace(p)  # Only this guarded synthetic file, never a user file.
    snapshot = {q: f.security(q) for q in f.before}
    with pytest.raises(SafetyError):
        f.restore()
    assert {q: f.security(q) for q in f.before} == snapshot


@pytest.mark.parametrize("uncertain", [False, True])
def test_partial_failure_recovery_requires_complete_matching_evidence(uncertain):
    f = FixtureAcl()
    with pytest.raises(SafetyError, match="partial"):
        f.repair(fail_after=2)
    if uncertain:
        # Missing acknowledgement must HOLD, never replay or partially roll back.
        f.after.pop(f.targets[1])
        snapshot = {p: f.security(p) for p in f.before}
        with pytest.raises(SafetyError):
            f.restore()
        assert {p: f.security(p) for p in f.before} == snapshot
    else:
        f.restore()
        assert {p: f.security(p) for p in f.before} == f.before


def test_fixture_writer_refuses_any_path_outside_the_new_managed_tree():
    f = FixtureAcl()
    outside = f.root.parent / "not-a-fixture-target"
    with pytest.raises(AssertionError):
        f.write(outside, f.trusted())
    assert not outside.exists()


def test_fresh_path_shim_conflicts_with_unchanged_private_arg0_contract():
    # Pinned CLI arg0/src/lib.rs creates apply_patch.bat below a fresh
    # CODEX_HOME/tmp/arg0-windows directory and prepends it to child PATH;
    # windows-sandbox-rs/src/env.rs inherits that PATH. An unreadable batch
    # cannot serve a sandboxed caller even when old helper files remain readable.
    from loop_engine.process import ProcessRunner

    f = FixtureAcl()
    f.repair()
    fresh = f.home / "tmp/arg0-windows/codex-arg0XYZ123"
    fresh.mkdir()
    batch = fresh / "apply_patch.bat"
    body = b"@echo off\r\nexit /b 37\r\n"
    batch.write_bytes(body)
    # A valid harmless batch works for the CLI owner using only system cmd.exe.
    # No model, auth, real account logon or network is involved.
    outcome = ProcessRunner().run(["cmd.exe", "/d", "/c", str(batch)], f.root, timeout=10)
    assert outcome.outcome == "exit" and outcome.returncode == 37
    assert not f.can_read_as_synthetic_group(batch, body)
    private_acl(f.security(f.home / "tmp/arg0-windows"), f.owner)


def test_readonly_noninheriting_home_preserves_fresh_shims_and_private_recreation():
    f = FixtureAcl()
    f.readonly_runtime_candidate()
    group_aces = [(mask, flags) for sid, mask, flags in f.security(f.home)[2] if sid == GROUP]
    assert group_aces == [(0x1200A9, 0)]
    for name in ["auth.json", "config.toml"]:
        private_acl(f.security(f.home / name), f.owner)
        assert not f.can_read_as_synthetic_group(f.home / name)
    for p, before in f.before.items():
        if p not in f.targets:
            assert f.security(p) == before
    fresh = f.home / "tmp/arg0-windows/codex-arg0XYZ123"
    fresh.mkdir()
    body = b"@echo off\r\nexit /b 37\r\n"
    (fresh / "apply_patch.bat").write_bytes(body)
    assert f.can_read_as_synthetic_group(fresh / "apply_patch.bat", body)
    # This ACL-only candidate is compatible with shim reads, but admission under
    # the currently approved private-root/Arg0Guard policy MUST remain BLOCKED.
    with pytest.raises(SafetyError):
        private_acl(f.security(f.home), f.owner)
    with pytest.raises(SafetyError):
        Arg0Guard(f.home, f.owner)
    f.restore()
    assert {p: f.security(p) for p in f.before} == f.before

    f.readonly_runtime_candidate()
    for name in ["auth.json", "config.toml"]:
        p = f.home / name
        saved = f.home / (name + ".synthetic-old")
        f.guard(saved)
        p.rename(saved)  # Move only a guarded canary; never a credential backup.
        p.write_bytes(b"SYNTHETIC_NOT_A_CREDENTIAL")
        private_acl(f.security(p), f.owner)
        assert not f.can_read_as_synthetic_group(p)
    snapshot = {p: f.security(p) for p in f.targets}
    with pytest.raises(SafetyError):
        f.restore()  # Safe inheritance does not authorize a changed identity.
    assert {p: f.security(p) for p in f.targets} == snapshot
