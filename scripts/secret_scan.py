"""Offline secret scan: fail on findings, print locations without secret values."""

import hashlib
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


def reviewed_public_reference(name: str, entry: dict[str, object]) -> bool:
    """Only five public integrity references in the exact owner-approved bytes."""
    if (
        name.replace("\\", "/").removeprefix("./")
        != "docs/plans/MODEL_BOUNDARY_APPROVAL_MANIFEST.json"
        or entry.get("type") != "Hex High Entropy String"
        or entry.get("line_number") not in {4, 7, 8, 9, 10}
    ):
        return False
    path = ROOT / "docs/plans/MODEL_BOUNDARY_APPROVAL_MANIFEST.json"
    # Public approval identity, not a credential. No mutable wildcard/file waiver.
    # pragma: allowlist nextline secret
    expected = "4c936fec3615b09d2352e1308dee8835bf20ec709ae14585efecd9b4d27ddcb4"
    return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected


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
    findings = {
        name: remaining
        for name, entries in findings.items()
        if (remaining := [entry for entry in entries if not reviewed_public_reference(name, entry)])
    }
    for name, entries in findings.items():
        print(f"Potential secret: {name}, lines {[entry['line_number'] for entry in entries]}")
    print(f"Offline secret scan: {sum(len(entries) for entries in findings.values())} findings")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
