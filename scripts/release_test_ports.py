"""Free the fixed ports the browser checks need, before they are needed.

Playwright is configured with `reuseExistingServer: false`, so it starts its own
API fixture and dev server. When a run aborts — a failed check, a killed loop —
it does not always take those servers down with it. The next run then dies on
"port is already in use", which has nothing to do with the change under test.
Two orphans had accumulated on 2026-11-17 and every frontend job after the first
failure would have failed for that reason alone.

Only this project's own test servers are ever stopped. A process is a candidate
solely because it is listening on one of these ports AND its command line names
one of our fixtures; anything else listening there is reported and left alone,
because guessing wrong here means killing something a person was using.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

PORTS = (8000, 5174)
# The fixture and the dev server, by the way they appear in a command line.
OURS = ("tests/e2e_server.py", "tests\\e2e_server.py", "e2e_server.py", "vite")


def is_ours(command: str) -> bool:
    """True only for this project's own test servers.

    Deliberately narrow: `python`, `node` or a bare port number is never enough.
    """
    lowered = command.lower()
    if not any(marker.lower() in lowered for marker in OURS):
        return False
    return "locus" in lowered or "e2e_server" in lowered


def listeners(port: int) -> list[int]:
    """PIDs listening on `port`, best effort, empty when it cannot be determined."""
    if sys.platform == "win32":
        argv = ["netstat", "-ano", "-p", "tcp"]
        pattern = re.compile(rf"TCP\s+\S*:{port}\s+\S+\s+LISTENING\s+(\d+)")
    else:
        argv = ["ss", "-ltnp"]
        pattern = re.compile(rf":{port}\s.*pid=(\d+)")
    try:
        out = subprocess.run(  # noqa: S603 — fixed system tool, no shell
            argv, capture_output=True, text=True, errors="replace", timeout=30, check=False
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    return sorted({int(m.group(1)) for m in pattern.finditer(out)})


def command_of(pid: int) -> str:
    if sys.platform == "win32":
        argv = [
            "powershell",
            "-NoProfile",
            "-Command",
            f"(Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}').CommandLine",
        ]
    else:
        argv = ["ps", "-o", "args=", "-p", str(pid)]
    try:
        return subprocess.run(  # noqa: S603 — fixed system tool, no shell
            argv, capture_output=True, text=True, errors="replace", timeout=30, check=False
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def stop(pid: int) -> bool:
    argv = (
        ["taskkill", "/PID", str(pid), "/F", "/T"]
        if sys.platform == "win32"
        else ["kill", "-9", str(pid)]
    )
    try:
        return (
            subprocess.run(  # noqa: S603 — fixed system tool, no shell
                argv, capture_output=True, text=True, timeout=30, check=False
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args()

    foreign = []
    for port in PORTS:
        for pid in listeners(port):
            command = command_of(pid)
            if not is_ours(command):
                foreign.append(f"port {port}: pid {pid} is not ours — {command[:90]}")
                continue
            if arguments.dry_run:
                print(f"would stop pid {pid} on port {port}")
            elif stop(pid):
                print(f"stopped the stale test server on port {port} (pid {pid})")
            else:
                foreign.append(f"port {port}: pid {pid} would not stop")
    if foreign:
        print("\n".join(foreign))
        print("The browser checks need these ports. Free them and run again.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
