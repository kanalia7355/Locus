"""Verify only the framework-independent engine; live readiness is a separate gate."""

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ["loop_engine", "tests/unit", "tests/integration", "tests/e2e", "scripts/verify_loop.py"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", action="store_true")
    args = parser.parse_args()
    commands = [
        ("lint", [sys.executable, "-m", "ruff", "check", *TARGETS]),
        ("format", [sys.executable, "-m", "ruff", "format", "--check", *TARGETS]),
        ("types", [sys.executable, "-m", "mypy", "loop_engine"]),
        (
            "python311-types",
            [
                sys.executable,
                "-m",
                "mypy",
                "--python-version",
                "3.11",
                "--platform",
                "linux",
                "loop_engine",
            ],
        ),
        (
            "tests",
            [sys.executable, "-m", "pytest", "-q", "tests/unit", "tests/integration", "tests/e2e"],
        ),
        ("secrets", [sys.executable, "scripts/secret_scan.py"]),
        ("dependency-consistency", [sys.executable, "-m", "pip", "check"]),
    ]
    if args.audit:
        commands.append(("dependency-advisories", [sys.executable, "-m", "pip_audit"]))
    results = []
    for name, command in commands:
        print(f"Running engine {name}", flush=True)
        started = time.monotonic()
        try:
            code = subprocess.run(command, cwd=ROOT, timeout=180, check=False).returncode  # noqa: S603
        except subprocess.TimeoutExpired:
            code = 124
        results.append(
            {
                "name": name,
                "exit_code": code,
                "elapsed_seconds": round(time.monotonic() - started, 2),
            }
        )
        if code:
            break
    directory = ROOT / ".loop/runtime"
    directory.mkdir(parents=True, exist_ok=True)
    passed = all(item["exit_code"] == 0 for item in results)
    (directory / "verification.json").write_text(
        json.dumps(
            {
                "at": datetime.now(UTC).isoformat(),
                "checks": results,
                "passed": passed,
                "live_execution_ready": False,
                "remote_integration_verified": False,
                "note": "Local/mock checks do not prove live isolation or atomic base binding.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
