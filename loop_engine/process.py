"""Bounded output, cooperative controls and owned process-tree lifetime containment."""

import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loop_engine.security import SafetyError, reparse, safe_environment


class WindowsJob:
    """Assign a suspended process before resuming; close kills all descendants."""

    def __init__(
        self, active_process_limit: int | None = None, *, require_settlement: bool = False
    ) -> None:
        import ctypes
        from ctypes import wintypes as w

        class Basic(ctypes.Structure):
            _fields_ = [
                ("process_time", ctypes.c_int64),
                ("job_time", ctypes.c_int64),
                ("flags", w.DWORD),
                ("min_working", ctypes.c_size_t),
                ("max_working", ctypes.c_size_t),
                ("active", w.DWORD),
                ("affinity", ctypes.c_size_t),
                ("priority", w.DWORD),
                ("scheduling", w.DWORD),
            ]

        class IO(ctypes.Structure):
            _fields_ = [
                (name, ctypes.c_uint64)
                for name in ("read_ops", "write_ops", "other_ops", "read", "write", "other")
            ]

        class Extended(ctypes.Structure):
            _fields_ = [
                ("basic", Basic),
                ("io", IO),
                ("process_memory", ctypes.c_size_t),
                ("job_memory", ctypes.c_size_t),
                ("peak_process", ctypes.c_size_t),
                ("peak_job", ctypes.c_size_t),
            ]

        self.require_settlement = require_settlement
        self.settled = False
        self.kernel = vars(ctypes)["WinDLL"]("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.restype = w.HANDLE
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
        self.kernel.SetInformationJobObject.argtypes = [
            w.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            w.DWORD,
        ]
        self.kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        self.kernel.OpenProcess.restype = w.HANDLE
        self.kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        self.kernel.CloseHandle.argtypes = [w.HANDLE]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        info = Extended()
        info.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if active_process_limit is not None:
            if type(active_process_limit) is not int or active_process_limit != 1:
                self.close()
                raise OSError("Only single-process audit containment is supported")
            info.basic.flags |= 0x8  # JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            info.basic.active = 1
        if not self.handle or not self.kernel.SetInformationJobObject(
            self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)
        ):
            self.close()
            raise OSError("Windows job containment unavailable")

    def attach_and_resume(
        self,
        process: subprocess.Popen[bytes],
        before_resume: Callable[[int, "WindowsJob"], None] | None = None,
    ) -> None:
        import ctypes
        from ctypes import wintypes as w

        handle = self.kernel.OpenProcess(0x0101, False, process.pid)
        if not handle:
            raise OSError("Cannot open owned child for job assignment")
        try:
            if not self.kernel.AssignProcessToJobObject(self.handle, handle):
                raise OSError("Cannot contain owned child process")
        finally:
            self.kernel.CloseHandle(handle)

        if before_resume is not None:
            before_resume(process.pid, self)

        class ThreadEntry(ctypes.Structure):
            _fields_ = [
                ("size", w.DWORD),
                ("usage", w.DWORD),
                ("id", w.DWORD),
                ("owner", w.DWORD),
                ("base", w.LONG),
                ("delta", w.LONG),
                ("flags", w.DWORD),
            ]

        self.kernel.CreateToolhelp32Snapshot.restype = w.HANDLE
        self.kernel.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
        self.kernel.Thread32First.argtypes = [w.HANDLE, ctypes.POINTER(ThreadEntry)]
        self.kernel.Thread32Next.argtypes = [w.HANDLE, ctypes.POINTER(ThreadEntry)]
        self.kernel.OpenThread.restype = w.HANDLE
        self.kernel.OpenThread.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        self.kernel.ResumeThread.argtypes = [w.HANDLE]
        self.kernel.ResumeThread.restype = w.DWORD
        snapshot = self.kernel.CreateToolhelp32Snapshot(4, 0)
        if snapshot == ctypes.c_void_p(-1).value:
            raise OSError("Cannot enumerate owned suspended thread")
        entry = ThreadEntry()
        entry.size = ctypes.sizeof(entry)
        resumed = False
        try:
            valid = self.kernel.Thread32First(snapshot, ctypes.byref(entry))
            while valid:
                if entry.owner == process.pid:
                    thread = self.kernel.OpenThread(2, False, entry.id)
                    if thread:
                        try:
                            resumed = self.kernel.ResumeThread(thread) != 0xFFFFFFFF or resumed
                        finally:
                            self.kernel.CloseHandle(thread)
                valid = self.kernel.Thread32Next(snapshot, ctypes.byref(entry))
        finally:
            self.kernel.CloseHandle(snapshot)
        if not resumed:
            raise OSError("Cannot resume contained child")

    def close(self) -> None:
        if getattr(self, "handle", None):
            try:
                if getattr(self, "require_settlement", False):
                    self._settle()
            finally:
                self.kernel.CloseHandle(self.handle)
                self.handle = None

    def _settle(self) -> None:
        """Bounded proof of an empty existing job before credential leases close."""
        import ctypes
        import struct
        from ctypes import wintypes as w

        self.kernel.QueryInformationJobObject.argtypes = [
            w.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            w.DWORD,
            ctypes.c_void_p,
        ]
        self.kernel.QueryInformationJobObject.restype = w.BOOL
        self.kernel.TerminateJobObject.argtypes = [w.HANDLE, w.UINT]
        self.kernel.TerminateJobObject.restype = w.BOOL
        end = time.monotonic() + 5  # Existing bounded cleanup, never a new execution budget.
        killed = False
        while True:
            accounting = ctypes.create_string_buffer(48)
            if not self.kernel.QueryInformationJobObject(self.handle, 1, accounting, 48, None):
                raise OSError("Process tree settlement unavailable")
            if struct.unpack_from("<I", accounting, 40)[0] == 0:
                self.settled = True
                return
            if not killed:
                if not self.kernel.TerminateJobObject(self.handle, 1):
                    raise OSError("Owned process tree could not be terminated")
                killed = True
            if time.monotonic() >= end:
                raise OSError("Process tree settlement deadline reached")
            time.sleep(0.01)


@dataclass
class ProcessResult:
    outcome: str
    returncode: int | None
    stdout: str = ""
    stderr: str = ""
    elapsed: float = 0
    tree_settled: bool | None = None


class ProcessRunner:
    def run(
        self,
        argv: list[str],
        cwd: Path,
        *,
        timeout: float,
        stdin: str = "",
        cancelled: Callable[[], bool] = lambda: False,
        model: bool = False,
        output_limit: int = 1_000_000,
        output_observer: Callable[[int, bytes], None] | None = None,
        active_process_limit: int | None = None,
        before_resume: Callable[[int, WindowsJob], None] | None = None,
        private_temp: Path | None = None,
        require_settlement: bool = False,
    ) -> ProcessResult:
        if timeout <= 0 or not argv:
            return ProcessResult(
                "unavailable", None, tree_settled=True if require_settlement else None
            )
        if cancelled():
            return ProcessResult(
                "cancelled", None, tree_settled=True if require_settlement else None
            )
        started = time.monotonic()
        job: WindowsJob | None = None
        process: subprocess.Popen[bytes] | None = None
        exceeded = threading.Event()
        buffers = [bytearray(), bytearray()]
        try:
            options: dict[str, Any] = {}
            if sys.platform == "win32":
                job = WindowsJob(active_process_limit, require_settlement=require_settlement)
                options["creationflags"] = (
                    0x00000004 | subprocess.CREATE_NO_WINDOW
                )  # CREATE_SUSPENDED
            else:
                if (
                    require_settlement
                    or active_process_limit is not None
                    or before_resume is not None
                ):
                    return ProcessResult("unavailable", None, tree_settled=True)
                options["start_new_session"] = True
            environment = safe_environment(model=model)
            if private_temp is not None:
                if not private_temp.is_dir() or any(
                    reparse(part) for part in (private_temp, *private_temp.parents)
                ):
                    raise SafetyError("Unsafe invocation temporary directory")
                environment.update(TEMP=str(private_temp), TMP=str(private_temp))
            process = subprocess.Popen(  # noqa: S603 — argv only, never shell
                argv,
                cwd=cwd,
                env=environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                **options,
            )
            if job:
                if before_resume is None:
                    job.attach_and_resume(process)
                else:
                    job.attach_and_resume(process, before_resume)

            def read(stream: Any, buffer: bytearray, channel: int) -> None:
                reader = stream.read1 if output_observer is not None else stream.read
                while chunk := reader(4096):
                    if len(buffer) + len(chunk) > output_limit:
                        exceeded.set()
                    if len(buffer) < output_limit:
                        buffer.extend(chunk[: output_limit - len(buffer)])
                    if output_observer is not None and not exceeded.is_set():
                        try:
                            output_observer(channel, chunk)
                        except Exception:
                            # Contain the consumer without a thread traceback.
                            exceeded.set()

            readers = [
                threading.Thread(target=read, args=(stream, buffer, channel), daemon=True)
                for channel, (stream, buffer) in enumerate(
                    zip((process.stdout, process.stderr), buffers, strict=True)
                )
            ]
            for reader in readers:
                reader.start()

            def write_input() -> None:
                if process is not None and process.stdin:
                    try:
                        process.stdin.write(stdin.encode("utf-8"))
                        process.stdin.close()
                    except (BrokenPipeError, OSError):
                        pass

            writer = threading.Thread(target=write_input, daemon=True)
            writer.start()
            outcome = "exit"
            while process.poll() is None:
                if exceeded.is_set() or cancelled() or time.monotonic() - started >= timeout:
                    outcome = (
                        "output_limit"
                        if exceeded.is_set()
                        else "cancelled"
                        if cancelled()
                        else "timeout"
                    )
                    self._terminate(process, job)
                    break
                time.sleep(0.03)
            process.wait(timeout=5)
            if job:
                job.close()  # Also terminates descendants left after their parent exited.
            for reader in readers:
                reader.join(3)
            writer.join(3)
            if exceeded.is_set():
                outcome = "output_limit"
            return ProcessResult(
                outcome,
                process.returncode,
                stdout=buffers[0].decode("utf-8", errors="replace"),
                stderr=buffers[1].decode("utf-8", errors="replace"),
                elapsed=round(time.monotonic() - started, 3),
                tree_settled=job.settled if job and require_settlement else None,
            )
        except (OSError, subprocess.SubprocessError):
            if process:
                self._terminate(process, job)
            return ProcessResult(
                "spawn_error",
                None,
                elapsed=round(time.monotonic() - started, 3),
                tree_settled=(process is None or (job is not None and job.settled))
                if require_settlement
                else None,
            )
        except BaseException:
            if process:
                self._terminate(process, job)
            raise
        finally:
            if job:
                job.close()

    @staticmethod
    def _terminate(process: subprocess.Popen[bytes], job: WindowsJob | None) -> None:
        if job:
            job.close()
        elif sys.platform != "win32" and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
