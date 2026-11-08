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
    if not commits or len(commits) > 200:
        local_base_ref = "origin/loop/local-development"
        try:
            branch_base = git("rev-parse", "--verify", local_base_ref + "^{commit}")
        except subprocess.CalledProcessError:
            branch_base = git("rev-parse", "--verify", "origin/main^{commit}")
        before = git("merge-base", branch_base, after)
        git("merge-base", "--is-ancestor", before, after)
        commits = git("rev-list", "--reverse", before + ".." + after).splitlines()
        if len(commits) > 200:
            raise ValueError("Fallback Push range is oversized and requires assessment")
        if not commits:
            print("No new commits in the branch-local Push range; validation succeeded.")
            return 0

    validated = 0
    for commit in commits:
        subject = git("show", "-s", "--format=%s", commit)
        parents = git("show", "-s", "--format=%P", commit).split()
        if subject.startswith("Merge ") or len(parents) >= 2:
            continue
        if not PATTERN.fullmatch(subject):
            raise ValueError("Push range contains a non-Conventional Commit")
        validated += 1
    if validated == 0:
        print("No new non-merge commits in the Push range; validation succeeded.")
    return validated


if __name__ == "__main__":
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    if os.environ.get("GITHUB_EVENT_NAME") != "push" or event.get("deleted") is not False:
        raise ValueError("Expected a branch Push")
    print("Validated Conventional Commits:", verify(Path.cwd(), event["before"], event["after"]))
