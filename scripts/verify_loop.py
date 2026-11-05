"""Verify only the framework-independent engine; live readiness is a separate gate."""

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ["loop_engine", "tests/unit", "tests/integration", "tests/e2e", "scripts/verify_loop.py"]


def windows_test_groups(timeout: float = 600) -> list[dict[str, Any]]:
    """Run the same suite in two processes sharing the original execution window.

    subprocess.run settles direct children on timeout, as the serial runner did.
    CI job cleanup remains the outer guard for descendant processes.
    """
    deadline = time.monotonic() + timeout
    groups = (("unit", ["tests/unit"]), ("integration-e2e", ["tests/integration", "tests/e2e"]))

    def run_group(group: tuple[str, list[str]]) -> dict[str, Any]:
        name, paths = group
        started = time.monotonic()
        remaining = deadline - started
        code, outcome = 124, "deadline_before_start"
        if remaining > 0:
            try:
                command = [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    "-o",
                    f"cache_dir=.loop/runtime/pytest-cache/{name}",
                    *paths,
                ]
                code = subprocess.run(  # noqa: S603
                    command, cwd=ROOT, timeout=remaining, check=False
                ).returncode
                outcome = "exit"
            except subprocess.TimeoutExpired:
                outcome = "timeout"
            except OSError:
                code, outcome = 125, "launch_error"
            except Exception:  # Fail closed, retain both results without logging arbitrary data.
                code, outcome = 125, "runner_error"
        return {
            "name": "tests-" + name,
            "exit_code": code,
            "outcome": outcome,
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }

    with ThreadPoolExecutor(max_workers=2) as executor:
        return list(executor.map(run_group, groups))


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
        if name == "tests" and sys.platform == "win32":
            # Windows PowerShell5.1 is a different runtime from the hosted pwsh
            # workflow shell. Separate its one-time cold startup from the actual
            # script assertions; all existing 20s test deadlines stay unchanged.
            from loop_engine.process import ProcessRunner

            startup_ok = True
            for phase, limit in (("cold", 45), ("warm", 20)):
                outcome = ProcessRunner().run(
                    [
                        "powershell.exe",
                        "-NoProfile",
                        "-NonInteractive",
                        "-Command",
                        "[Console]::Out.WriteLine('locus-powershell-ready')",
                    ],
                    ROOT,
                    timeout=limit,
                )
                startup_ok = (
                    outcome.outcome == "exit"
                    and outcome.returncode == 0
                    and outcome.stdout.strip() == "locus-powershell-ready"
                )
                evidence = {
                    "name": "windows-powershell-" + phase,
                    "exit_code": 0 if startup_ok else 1,
                    "elapsed_seconds": outcome.elapsed,
                    "outcome": outcome.outcome,
                }
                print(json.dumps(evidence), flush=True)
                results.append(evidence)
                if not startup_ok:
                    break
            if not startup_ok:
                break
        print(f"Running engine {name}", flush=True)
        started = time.monotonic()
        try:
            if name == "tests" and sys.platform == "win32":
                partitions = windows_test_groups()
                results.extend(partitions)
                for result in partitions:
                    print(json.dumps(result), flush=True)
                code = next(
                    (result["exit_code"] for result in partitions if result["exit_code"]), 0
                )
            else:
                code = subprocess.run(  # noqa: S603
                    command, cwd=ROOT, timeout=600 if name == "tests" else 180, check=False
                ).returncode
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
