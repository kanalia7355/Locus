"""Offline secret scan: fail on findings, print locations without secret values."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = (
    r"(^|[/\\])(\.git|\.venv|node_modules|dist|storage|test-results|playwright-report|"
    r"\.mypy_cache|\.ruff_cache|\.pytest_cache|__pycache__)([/\\]|$)|"
    r"\.(zip|png|tsbuildinfo)$|\.bootstrap/.*-audit\.json$"
)
SYNTHETIC = (
    r"^(Temporary-password-0[1-4]!|Changed-password-long-01!|"
    r"Synthetic-test-password-01!|Changed-synthetic-password-01!)$"
)


def main() -> int:
    result = subprocess.run(  # noqa: S603 — fixed interpreter/module, no shell
        [
            sys.executable,
            "-m",
            "detect_secrets",
            "-c",
            "2",
            "scan",
            "--all-files",
            "--no-verify",
            "--exclude-files",
            EXCLUDED,
            "--exclude-secrets",
            SYNTHETIC,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    if result.returncode:
        print("Secret scanner failed; review local tool setup.")
        return result.returncode
    report = json.loads(result.stdout)
    findings = report["results"]
    for name, entries in findings.items():
        print(f"Potential secret: {name}, lines {[entry['line_number'] for entry in entries]}")
    print(f"Offline secret scan: {sum(len(entries) for entries in findings.values())} findings")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
