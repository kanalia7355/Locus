"""Run reproducible checks with finite timeouts and record actual exit codes."""

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NPM = "npm.cmd" if sys.platform == "win32" else "npm"


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
        (
            "python-tests",
            [sys.executable, "-m", "pytest", "-q", "--cov", "--cov-report=term-missing"],
            ROOT,
            120,
        ),
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
            code = subprocess.run(command, cwd=cwd, timeout=timeout, check=False).returncode  # noqa: S603
        except subprocess.TimeoutExpired:
            code = 124
        results.append(
            {
                "name": name,
                "command": command[1:],
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
