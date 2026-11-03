"""Synthetic namespace only. No operator auth/config or actual CLI lifecycle."""

import sys
import time
from pathlib import Path

import pytest

from loop_engine.c_min_runtime import file_security, private_directory
from loop_engine.process import ProcessRunner
from loop_engine.security import SafetyError
from loop_engine.trial_arg0 import Arg0Guard
from loop_engine.windows_pipe import Native


@pytest.mark.skipif(sys.platform != "win32", reason="Real Win32 metadata handles")
@pytest.mark.parametrize("mode", ["success", "extra", "stale", "foreign", "replaced", "expired"])
def test_synthetic_arg0_retained_metadata_and_failures(tmp_path, mode):
    owner = Native().current_sid()
    home = tmp_path / "synthetic-home"
    home.mkdir()

    def command(path, *args):
        # Only this fresh synthetic test tree. Elevated Windows may default the
        # owner to Administrators; valid input requires the exact operator SID.
        assert path.resolve().is_relative_to(tmp_path.resolve())
        result = ProcessRunner().run(["icacls.exe", str(path), *args], tmp_path, timeout=10)
        assert result.outcome == "exit" and result.returncode == 0

    def assign_owner(path, recursive=False):
        if file_security(path)[0] != owner:
            command(path, "/setowner", "*" + owner, *(["/T"] if recursive else []))
        assert file_security(path)[0] == owner

    assign_owner(home)
    command(
        home,
        "/inheritance:r",
        "/grant:r",
        "*" + owner + ":(OI)(CI)(M)",
        "*S-1-5-18:(OI)(CI)(F)",
        "*S-1-5-32-544:(OI)(CI)(F)",
    )
    assert private_directory(tmp_path, "synthetic-home") == home  # all strict checks unchanged
    root = home / "tmp/arg0-windows"
    root.mkdir(parents=True)
    if mode == "stale":
        (root / "codex-arg0ABC123").mkdir()
    assign_owner(home / "tmp", recursive=True)
    cancelled = [False]

    def remaining():
        if cancelled[0]:
            raise SafetyError("expired synthetic trial")

    guard = Arg0Guard(home, Native().current_sid(), remaining)
    guard.native.kernel.ReadFile = lambda *args: pytest.fail("metadata must not read data")
    path = root / "codex-arg0ABC123"
    path.mkdir(exist_ok=True)
    for name in (".lock", "apply_patch.bat", "applypatch.bat"):
        (path / name).write_bytes(b"synthetic not executable")
    assign_owner(path, recursive=True)
    if mode == "extra":
        (path / "unknown").touch()
    text = str(path.parent if mode == "foreign" else path)
    try:
        if mode in {"extra", "stale", "foreign"}:
            with pytest.raises(SafetyError):
                guard.check(text, time.time() - 2, time.time() + 2)
        else:
            first = guard.check(text, time.time() - 2, time.time() + 2)
            assert guard.handles
            assert first["index"] == path.stat().st_ino
            if mode == "replaced":
                with pytest.raises(OSError):
                    path.rename(root / "codex-arg0DEF456")  # no delete sharing
            elif mode == "expired":
                cancelled[0] = True
                with pytest.raises(SafetyError):
                    guard.check(text, time.time() - 2, time.time() + 2)
            else:
                assert first == guard.check(text, time.time() - 2, time.time() + 2)
    finally:
        guard.close()
    assert not guard.handles


@pytest.mark.parametrize("mode", ["oversize", "reparse", "expired"])
def test_prelaunch_snapshot_is_bounded_before_native_access(tmp_path, monkeypatch, mode):
    monkeypatch.setattr("loop_engine.trial_arg0.Native", lambda: object())
    home = tmp_path / "synthetic"
    root = home / "tmp/arg0-windows"
    root.mkdir(parents=True)
    if mode == "oversize":
        for index in range(257):
            (root / str(index)).touch()
    if mode == "reparse":
        monkeypatch.setattr("loop_engine.trial_arg0.reparse", lambda path: path == root)

    def remaining():
        if mode == "expired":
            raise SafetyError("expired")

    with pytest.raises(SafetyError):
        Arg0Guard(home, "synthetic", remaining)


def test_no_auth_file_content_access(tmp_path, monkeypatch):
    original = Path.open

    def checked(path, *args, **kwargs):
        assert path.name not in {"auth.json", "codex_auth.age"}
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", checked)
    monkeypatch.setattr("loop_engine.trial_arg0.Native", lambda: object())
    with pytest.raises(SafetyError):
        Arg0Guard(tmp_path / "synthetic", "synthetic")
