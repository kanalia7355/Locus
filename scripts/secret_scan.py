"""Offline secret scan: fail on findings, print locations without secret values."""

import json
import shutil
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
    executable = shutil.which("git")
    inventory = (
        subprocess.run(  # noqa: S603 — fixed read-only Git source inventory
            [executable, "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        if executable
        else None
    )
    paths = ["."]  # Source archives without Git retain the original full-tree scan.
    if inventory is not None and inventory.returncode == 0:
        paths = [
            "./" + name
            for name in sorted(set(filter(None, inventory.stdout.split("\0"))))
            if (ROOT / name).is_file()
        ]
        if not paths:
            print("Offline secret scan: no publishable source files")
            return 0
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
            *paths,
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
