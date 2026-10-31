"""Trusted PID1: an unprivileged workload cannot extend a dead controller's lease."""

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath


def drop_identity() -> None:
    vars(os)["setgroups"]([])
    vars(os)["setgid"](1000)
    vars(os)["setuid"](1000)


def main() -> int:
    if vars(os)["getuid"]() != 0 or not sys.argv[1:]:
        return 125
    lease = Path("/lease/heartbeat")
    closed = Path("/lease/closed")
    maximum = float(os.environ["LOCUS_MAX_SECONDS"])
    if not 0 < maximum <= 1800 or closed.exists():
        return 124
    started = time.monotonic()
    seen = lease.stat().st_mtime_ns
    renewed = started
    signal.signal(signal.SIGTERM, lambda *_: os._exit(143))
    signal.signal(signal.SIGINT, lambda *_: os._exit(130))
    work = Path("/tmp/work")  # noqa: S108 — private container tmpfs, never a host path
    work.mkdir()
    names = json.loads(Path("/lease/source-files.json").read_text(encoding="utf-8"))
    if not isinstance(names, list) or len(names) > 3000:
        return 125
    for name in names:
        relative = PurePosixPath(name)
        if (
            relative.is_absolute()
            or any(part in {"..", ".git"} for part in relative.parts)
            or str(relative) != name
        ):
            return 125
        source = Path("/source") / name
        if any(path.is_symlink() for path in [source, *source.parents]):
            return 125
        target = work / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    virtual = work / ".venv/bin"
    if (work / ".venv").exists():
        return 125
    virtual.mkdir(parents=True)
    (virtual / "python").symlink_to(sys.executable)
    node_modules = work / "frontend/node_modules"
    if node_modules.parent.is_dir() and not node_modules.exists():
        node_modules.symlink_to("/opt/node/node_modules", target_is_directory=True)
    readonly = os.environ.get("LOCUS_READONLY") == "1"
    for path in [work, *work.rglob("*")]:
        if path.is_symlink():
            continue
        if readonly:
            path.chmod(0o555 if path.is_dir() else 0o444)
        else:
            vars(os)["chown"](path, 1000, 1000)
    if closed.exists() or time.monotonic() - started >= maximum:
        return 124
    process = subprocess.Popen(sys.argv[1:], cwd=work, preexec_fn=drop_identity)  # noqa: S603 — Controller argv; fixed isolated identity
    while process.poll() is None:
        try:
            changed = lease.stat().st_mtime_ns
            if changed != seen:
                seen, renewed = changed, time.monotonic()
            if (
                closed.exists()
                or time.monotonic() - started >= maximum
                or time.monotonic() - renewed > 8
            ):
                os._exit(124)  # PID namespace teardown kills every descendant, even setsid().
        except OSError:
            os._exit(124)
        time.sleep(0.25)
    return int(process.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
