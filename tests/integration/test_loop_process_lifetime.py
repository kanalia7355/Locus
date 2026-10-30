import ctypes
import subprocess
import sys
import time
from pathlib import Path

import pytest


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows containment only; POSIX parent-death proof unavailable",
)
def test_forced_controller_exit_kills_owned_child(tmp_path: Path) -> None:
    pid_path = tmp_path / "owned-child.pid"
    child_code = (
        f"import os,time;open({str(pid_path)!r},'w').write(str(os.getpid()));time.sleep(60)"
    )
    supervisor = (
        "import sys;from pathlib import Path;from loop_engine.process import ProcessRunner;"
        f'ProcessRunner().run([sys.executable,"-c",{child_code!r}],Path({str(tmp_path)!r}),timeout=60)'
    )
    parent = subprocess.Popen(  # noqa: S603 — owned synthetic process fixture
        [sys.executable, "-c", supervisor], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )  # noqa: S603
    try:
        deadline = time.monotonic() + 8
        while not pid_path.exists() and time.monotonic() < deadline:
            time.sleep(0.03)
        assert pid_path.exists(), "Contained child did not start"
        child_pid = int(pid_path.read_text())
        parent.kill()
        parent.wait(timeout=5)
        from ctypes import wintypes as w

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = w.HANDLE
        kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        kernel.GetExitCodeProcess.argtypes = [w.HANDLE, ctypes.POINTER(w.DWORD)]
        kernel.CloseHandle.argtypes = [w.HANDLE]
        deadline = time.monotonic() + 5
        alive = True
        while alive and time.monotonic() < deadline:
            handle = kernel.OpenProcess(0x1000, False, child_pid)
            if not handle:
                alive = False
            else:
                try:
                    code = w.DWORD()
                    alive = (
                        bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code)))
                        and code.value == 259
                    )
                finally:
                    kernel.CloseHandle(handle)
            if alive:
                time.sleep(0.03)
        assert not alive, "Child survived the owning controller Job handle closing"
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=5)
