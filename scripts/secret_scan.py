"""Offline secret scan: fail on findings, print locations without secret values."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def chosen_root() -> Path:
    """The tree to scan: `--root <path>` if given, otherwise this checkout.

    A job's gate runs the controller's own copy of this script so that fixing
    the instrument fixes every job at once — and so a job cannot change the
    instrument that judges it. The tree being scanned is then not the tree the
    script lives in, which is what `--root` says. Without it, the gate ran the
    *workspace's* stale copy: a fix made at 04:35 on 2026-11-22 still failed
    `T-PH7-201` at 05:10 because that workspace's copy predated it.
    """
    argv = sys.argv[1:]
    if "--root" in argv:
        return Path(argv[argv.index("--root") + 1]).resolve()
    return Path(__file__).resolve().parents[1]


ROOT = chosen_root()
EXCLUDED = (
    r"(^|[/\\])(\.git|\.venv|node_modules|dist|storage|test-results|playwright-report|"
    r"\.mypy_cache|\.ruff_cache|\.pytest_cache|__pycache__)([/\\]|$)|"
    r"\.(zip|png|tsbuildinfo)$|\.bootstrap/.*-audit\.json$"
)
# Exact synthetic fixtures, anchored, with no wildcard and no file waiver — the
# same rule as `reviewed_public_reference` below. A test that proves a key never
# reaches an audit record needs a key-shaped literal to plant, and on 2026-11-22
# `T-AIC-005` was failed by this gate for `sk-live-SUPERSECRET` and
# `sk-test-injected-key`, which is the correct test written the correct way. The
# answer is a named fixture, not a pattern: anything outside this closed set
# still fails, so a real key cannot be waved through by looking test-ish.
SYNTHETIC = (
    r"^(Temporary-password-0[1-4]!|Changed-password-long-01!|"
    r"Synthetic-test-password-01!|Changed-synthetic-password-01!|"
    r"sk-synthetic-0[1-4]-not-a-real-key)$"
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
    # Named paths scan only those, which is how a job's gate asks "did *this
    # change* introduce a secret". Without arguments the whole publishable
    # inventory is scanned, which is what CI and a person want. The difference
    # matters: on 2026-11-22 a full-tree gate failed `T-PH7-201` for a finding in
    # `T-PH7-222`'s recorded report — a different job's prose, in a file the
    # attempt never touched.
    argv = sys.argv[1:]
    if "--root" in argv:
        index = argv.index("--root")
        argv = argv[:index] + argv[index + 2 :]
    wanted = [argument for argument in argv if not argument.startswith("-")]
    if wanted:
        present = ["./" + name.replace("\\", "/") for name in wanted if (ROOT / name).is_file()]
        if not present:
            print("Offline secret scan: none of the named paths exist")
            return 0
        return scan(present)
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
    return scan(paths)


def scan(paths: list[str]) -> int:
    # The scanner reads sources with the interpreter's default encoding and
    # silently skips files it cannot decode. On a non-UTF-8 locale (Windows
    # cp932) that hid every finding in a file containing Japanese text, so the
    # local gate reported 0 while the UTF-8 hosted runners reported findings.
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
        env={**os.environ, "PYTHONUTF8": "1"},
        timeout=120,
    )
    if result.returncode:
        print("Secret scanner failed; review local tool setup.")
        return result.returncode
    findings = json.loads(result.stdout)["results"]
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
