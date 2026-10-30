import ctypes
import sys
from types import SimpleNamespace
from typing import Any

import pytest

from loop_engine.process import WindowsJob


@pytest.mark.skipif(sys.platform != "win32", reason="Win32 DWORD ABI is Windows-specific")
def test_failed_windows_resume_is_not_treated_as_success() -> None:
    from ctypes import wintypes as w

    def first(unused: Any, entry: Any) -> bool:
        entry._obj.owner = 42
        entry._obj.id = 1
        return True

    callback = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p)(lambda unused: -1)
    kernel = SimpleNamespace(
        OpenProcess=lambda *unused: 1,
        AssignProcessToJobObject=lambda *unused: True,
        CloseHandle=lambda *unused: None,
        CreateToolhelp32Snapshot=lambda *unused: 1,
        Thread32First=first,
        Thread32Next=lambda *unused: False,
        OpenThread=lambda *unused: 1,
        ResumeThread=callback,
    )
    job = object.__new__(WindowsJob)
    job.kernel = kernel
    job.handle = 1
    with pytest.raises(OSError, match="Cannot resume"):
        job.attach_and_resume(SimpleNamespace(pid=42))  # type: ignore[arg-type]
    assert callback.restype is w.DWORD
