"""Run reproducible checks with finite timeouts and record actual exit codes."""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

if __package__:
    from .verify_loop import bounded_test_groups
else:
    from verify_loop import bounded_test_groups

ROOT = Path(__file__).resolve().parents[1]
NPM = "npm.cmd" if sys.platform == "win32" else "npm"

PYTHON_GROUPS = (
    ("quality-integration", ["tests/integration", "tests/e2e"]),
    ("quality-remaining", ["tests", "--ignore=tests/integration", "--ignore=tests/e2e"]),
)


def python_test_checks(
    root: Path, timeout: float, *, deadline: float | None = None
) -> list[dict[str, Any]]:
    own_deadline = time.monotonic() + timeout
    deadline = own_deadline if deadline is None else min(deadline, own_deadline)
    directory = root / ".loop/runtime/coverage" / uuid4().hex
    directory.mkdir(parents=True)
    files = {name: directory / name for name, _ in PYTHON_GROUPS}
    environments = {
        name: {**os.environ, "COVERAGE_FILE": str(path.resolve())} for name, path in files.items()
    }
    checks = bounded_test_groups(
        PYTHON_GROUPS,
        timeout=timeout,
        deadline=deadline,
        cwd=root,
        extra_args=("--cov", "--cov-report="),
        environments=environments,
    )
    if any(item["exit_code"] for item in checks):
        return checks
    if not all(path.is_file() for path in files.values()):
        checks.append(
            {
                "name": "coverage-data",
                "exit_code": 1,
                "outcome": "missing_current_data",
                "command": [],
            }
        )
        return checks
    combined = directory / "combined"
    commands = (
        (
            "coverage-combine",
            [
                sys.executable,
                "-m",
                "coverage",
                "combine",
                f"--data-file={combined}",
                "--keep",
                *(str(path) for path in files.values()),
            ],
        ),
        (
            "coverage-report",
            [
                sys.executable,
                "-m",
                "coverage",
                "report",
                f"--data-file={combined}",
                "--show-missing",
            ],
        ),
    )
    for name, command in commands:
        started = time.monotonic()
        remaining = min(timeout, deadline - started)
        code, outcome = 124, "deadline_before_start"
        if remaining > 0:
            try:
                code = subprocess.run(command, cwd=root, timeout=remaining, check=False).returncode  # noqa: S603
                outcome = "exit"
            except subprocess.TimeoutExpired:
                outcome = "timeout"
            except OSError:
                code, outcome = 125, "launch_error"
        checks.append(
            {
                "name": name,
                "exit_code": code,
                "outcome": outcome,
                "command": command[1:],
                "elapsed_seconds": round(time.monotonic() - started, 2),
            }
        )
        if code:
            break
    return checks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--e2e", action="store_true")
    parser.add_argument(
        "--audit", action="store_true", help="Network calls to package advisory services"
    )
    args = parser.parse_args()
    commands: list[tuple[str, list[str], Path, int]] = [
        ("python-dependencies", [sys.executable, "-m", "pip", "check"], ROOT, 60),
        (
            "python-lint",
            [sys.executable, "-m", "ruff", "check", "backend", "tests", "scripts"],
            ROOT,
            60,
        ),
        (
            "python-format",
            [sys.executable, "-m", "ruff", "format", "--check", "backend", "tests", "scripts"],
            ROOT,
            60,
        ),
        ("python-types", [sys.executable, "-m", "mypy", "backend/app"], ROOT, 120),
        ("python-tests", [], ROOT, 120),  # Actual group commands are recorded below.
        ("secret-scan", [sys.executable, "scripts/secret_scan.py"], ROOT, 150),
        ("frontend-lint", [NPM, "run", "lint"], ROOT / "frontend", 120),
        ("frontend-tests", [NPM, "test"], ROOT / "frontend", 120),
        ("frontend-build", [NPM, "run", "build"], ROOT / "frontend", 120),
    ]
    if args.e2e:
        commands.append(("browser-e2e", [NPM, "run", "test:e2e"], ROOT / "frontend", 300))
    if args.audit:
        commands.extend(
            [
                ("python-advisories", [sys.executable, "-m", "pip_audit"], ROOT, 180),
                ("npm-advisories", [NPM, "audit", "--audit-level=low"], ROOT / "frontend", 120),
            ]
        )
    results = []
    for name, command, cwd, timeout in commands:
        print(f"\nRunning {name}", flush=True)
        started = time.monotonic()
        try:
            if name == "python-tests":
                checks = python_test_checks(ROOT, timeout, deadline=started + timeout)
                results.extend(checks)
                for check in checks:
                    print(json.dumps(check), flush=True)
                code = next((item["exit_code"] for item in checks if item["exit_code"]), 0)
            else:
                code = subprocess.run(command, cwd=cwd, timeout=timeout, check=False).returncode  # noqa: S603
        except subprocess.TimeoutExpired:
            code = 124
        except (OSError, ValueError):
            code = 125
        results.append(
            {
                "name": name,
                "command": [] if name == "python-tests" else command[1:],
                "exit_code": code,
                "elapsed_seconds": round(time.monotonic() - started, 2),
            }
        )
        if code:
            break
    output = {
        "at": datetime.now(UTC).isoformat(),
        "checks": results,
        "passed": all(item["exit_code"] == 0 for item in results),
        "requested_e2e": args.e2e,
        "requested_audit": args.audit,
    }
    (ROOT / ".bootstrap" / "verification.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0 if output["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
