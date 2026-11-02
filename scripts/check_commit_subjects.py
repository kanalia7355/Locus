"""Additive Push counterpart of the existing PR-title validation, no network."""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

PATTERN = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)"
    r"(\([a-z0-9][a-z0-9._/-]*\))?!?: .{1,100}$"
)


def verify(root: Path, before: str, after: str) -> int:
    binary = shutil.which("git")
    if binary is None:
        raise ValueError("Git unavailable")
    def git(*args: str) -> str:
        return subprocess.run(  # noqa: S603
            [binary, *args], cwd=root, check=True, capture_output=True, text=True, timeout=20
        ).stdout.strip()

    if not all(re.fullmatch(r"[0-9a-f]{40}", x) for x in (before, after)):
        raise ValueError("Invalid commit identity")
    if after == "0" * 40 or git("rev-parse", "HEAD") != after:
        raise ValueError("Deleted or mismatched Push target")
    if before == "0" * 40:
        before = git("merge-base", "origin/main", after)
    git("merge-base", "--is-ancestor", before, after)
    commits = git("rev-list", "--reverse", before + ".." + after).splitlines()
    if not 1 <= len(commits) <= 200:
        raise ValueError("Empty or oversized Push range requires assessment")
    for commit in commits:
        if not PATTERN.fullmatch(git("show", "-s", "--format=%s", commit)):
            raise ValueError("Push range contains a non-Conventional Commit")
    return len(commits)


if __name__ == "__main__":
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    if os.environ.get("GITHUB_EVENT_NAME") != "push" or event.get("deleted") is not False:
        raise ValueError("Expected a branch Push")
    print("Validated Conventional Commits:", verify(Path.cwd(), event["before"], event["after"]))
