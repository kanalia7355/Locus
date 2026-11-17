"""Freeing a port must never become a licence to kill the wrong process."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ports", ROOT / "scripts" / "release_test_ports.py")
assert SPEC and SPEC.loader
ports = importlib.util.module_from_spec(SPEC)
sys.modules["ports"] = ports
SPEC.loader.exec_module(ports)


def test_only_this_projects_own_test_servers_are_candidates() -> None:
    ours = [
        r'"C:\Users\hirot\Locus\.venv\Scripts\python.exe" ../tests/e2e_server.py',
        "/home/runner/work/Locus/Locus/.venv/bin/python tests/e2e_server.py",
        r"node C:\Users\hirot\Locus\frontend\node_modules\vite\bin\vite.js",
    ]
    for command in ours:
        assert ports.is_ours(command), command

    # Everything else on the same port belongs to someone, and killing it is
    # worse than failing the check.
    others = [
        "python",
        "python manage.py runserver 0.0.0.0:8000",
        "node server.js --port 8000",
        "C:\\Program Files\\PostgreSQL\\bin\\postgres.exe",
        "",
        "8000",
        "python -m http.server 8000",
    ]
    for command in others:
        assert not ports.is_ours(command), command


def test_a_process_it_may_not_stop_is_reported_not_killed(monkeypatch) -> None:
    killed: list[int] = []
    monkeypatch.setattr(ports, "listeners", lambda port: [4242] if port == 8000 else [])
    monkeypatch.setattr(ports, "command_of", lambda pid: "python -m http.server 8000")
    monkeypatch.setattr(ports, "stop", lambda pid: killed.append(pid) or True)
    monkeypatch.setattr(sys, "argv", ["release_test_ports.py"])
    assert ports.main() == 1, "an unknown holder must fail the check"
    assert killed == [], "and must not be killed"


def test_our_own_stale_server_is_stopped(monkeypatch) -> None:
    killed: list[int] = []
    monkeypatch.setattr(
        ports, "listeners", lambda port: [99] if port == 8000 and not killed else []
    )
    monkeypatch.setattr(
        ports, "command_of", lambda pid: r"C:\x\Locus\.venv\python.exe tests/e2e_server.py"
    )
    monkeypatch.setattr(ports, "stop", lambda pid: killed.append(pid) or True)
    monkeypatch.setattr(sys, "argv", ["release_test_ports.py"])
    assert ports.main() == 0
    assert killed == [99]


def test_a_port_that_never_frees_is_a_failure_not_a_silent_pass(monkeypatch) -> None:
    # Killing the process does not free the socket at once on Windows. If the
    # gate returned success anyway, Playwright would fail to bind a moment later
    # and the job would be blamed for it.
    monkeypatch.setattr(ports, "listeners", lambda port: [99] if port == 8000 else [])
    monkeypatch.setattr(ports, "command_of", lambda pid: "python Locus/tests/e2e_server.py")
    monkeypatch.setattr(ports, "stop", lambda pid: True)
    monkeypatch.setattr(ports, "WAIT_SECONDS", 0.2)
    monkeypatch.setattr(ports, "freed", lambda port, wait=0.2: False)
    monkeypatch.setattr(sys, "argv", ["release_test_ports.py"])
    assert ports.main() == 1
