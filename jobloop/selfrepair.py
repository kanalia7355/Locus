"""Recover from the failures that are the loop's own, and only those.

Over 2026-11-17/18 the queue stopped eight times. Five of those stops were not
the job's fault at all: the browser checks left their run record where the scope
gate counted it as an out-of-scope change; the controller wrote the main
checkout's path into a job file and then refused to dispatch that file; the
controller's own generated guide sat uncommitted and blocked the next merge.
Each one needed a person to read the evidence and say "that is ours, carry on".

That reading is mechanical for a known set of signatures, so it is done here.

The line this module does not cross: a repair may clean up after the tooling,
undo what the controller itself wrote, and give the job its attempt back. It may
never widen `allowed_paths`, weaken an acceptance criterion, mark anything done,
or forgive something a worker did. Those are judgements, and a judgement that
the loop makes for itself is not a judgement — it is a loop grading its own
homework. Everything outside the signatures below still goes to the owner, and
goes with a better description of what actually happened.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Files the tooling creates while checking. A job is never responsible for these.
TOOLING = (
    "test-results/",
    "playwright-report/",
    "frontend/test-results/",
    "frontend/playwright-report/",
    ".last-run.json",
)
# Written by the loop itself every time it raises a question.
LOOP_OWNED = ("docs/report/OWNER_DECISIONS_PLAIN_GUIDE.html",)

PATHS = re.compile(r"outside allowed_paths: \[(.*?)\]", re.DOTALL)
DIRTY = re.compile(r"^\s*[A-Z?]{1,2}\s+(.+)$", re.MULTILINE)


@dataclass(frozen=True)
class Repair:
    """What to do, and the sentence that will be recorded for having done it."""

    action: str  # "clean" | "redact" | "sweep"
    reason: str
    paths: tuple[str, ...] = ()

    @property
    def line(self) -> str:
        return f"{self.action}: {self.reason}"


def quoted(blob: str) -> tuple[str, ...]:
    """The paths in a `['a', 'b']` fragment, in order."""
    return tuple(found.group(1) for found in re.finditer(r"'([^']+)'", blob))


def is_tooling(path: str) -> bool:
    name = path.replace("\\", "/")
    return any(
        name == marker or name.startswith(marker) or name.endswith(marker) for marker in TOOLING
    )


def classify(category: str, context: str, *, repository: str = "") -> Repair | None:
    """The repair for a known self-inflicted stop, or None to leave it alone."""
    if category == "out-of-scope change":
        found = PATHS.search(context)
        if not found:
            return None
        paths = quoted(found.group(1))
        # Only when *every* path is the tooling's. One file the worker made is
        # a real deviation, and mixing the two would forgive it by accident.
        if paths and all(is_tooling(path) for path in paths):
            return Repair(
                "clean",
                "every path reported outside the scope was written by the checks "
                "themselves, not by the worker",
                paths,
            )
        return None

    if category == "the job file names another checkout" and repository:
        # The controller records gate output verbatim; a failure that quoted a
        # real command put the main checkout's path into the job file, and the
        # guard then refused to dispatch it. The loop poisoned itself.
        #
        # But only in the evidence. The same path in the frontmatter is the
        # ticket being wrong — a `test_cmd` naming an interpreter in another
        # checkout, which is what caused the containment failures in the first
        # place. Redacting that would leave a broken command and dispatch it.
        if "frontmatter=yes" in context:
            return None
        if repository in context:
            return Repair(
                "redact",
                "the path came from evidence the controller itself recorded, "
                "not from the job definition",
                (repository,),
            )
        return None

    if category == "integration branch is dirty":
        dirty = tuple(
            line.strip().strip('"').replace("\\", "/")
            for line in DIRTY.findall(context)
            if line.strip()
        )
        if dirty and all(path in LOOP_OWNED for path in dirty):
            return Repair(
                "sweep",
                "the only uncommitted file is the page the loop regenerates "
                "whenever it raises a question",
                dirty,
            )
        return None

    return None


def describe(category: str, context: str) -> str:
    """A better sentence for the owner when there is no repair to make.

    An escalation that says only "out-of-scope change" sends a person to read
    the diff. Saying which paths, and whose they are, usually answers it.
    """
    if category == "out-of-scope change":
        found = PATHS.search(context)
        paths = quoted(found.group(1)) if found else ()
        theirs = [path for path in paths if not is_tooling(path)]
        if theirs:
            return (
                f"{len(theirs)} path(s) the worker wrote outside its scope: "
                f"{', '.join(theirs[:6])}"
                + ("…" if len(theirs) > 6 else "")
                + ". Decide whether the job's scope was drawn too narrowly, or "
                "whether the worker should not have written them."
            )
    return ""
