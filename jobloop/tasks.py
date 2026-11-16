"""Read and update the task files that agents collaborate through.

`docs/agent/PROTOCOL.md` fixes the format: a leading `---` block of single-line
scalars, then prose sections. Updates here keep every byte outside the touched
field or section, including the file's existing line endings, so a controller
edit never rewrites a worker's report.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

STATUSES = ("todo", "doing", "review", "qa", "done", "blocked")
ATTEMPT_LIMIT = 3
REVIEW_CYCLE_LIMIT = 2
FIELD = re.compile(r"^([A-Za-z0-9_-]+):\s*(.*)$")


class TaskFormatError(ValueError):
    """The file does not match the protocol's frontmatter contract."""


@dataclass(frozen=True)
class Task:
    """One job: its protocol fields and the body that carries the evidence."""

    path: Path
    fields: dict[str, str]
    body: str
    newline: str = "\n"

    @property
    def id(self) -> str:
        return self.fields.get("id", "")

    @property
    def status(self) -> str:
        return self.fields.get("status", "")

    @property
    def attempts(self) -> int:
        try:
            return int(self.fields.get("attempts", "0"))
        except ValueError as error:
            raise TaskFormatError(f"{self.path}: attempts is not an integer") from error

    @property
    def weight(self) -> str:
        return self.fields.get("weight", "")

    @property
    def model(self) -> str:
        return self.fields.get("model", "")

    @property
    def reviewer(self) -> str:
        return self.fields.get("reviewer", "")

    @property
    def test_command(self) -> str:
        return self.fields.get("test_cmd", "").strip()

    @property
    def allowed_paths(self) -> list[str]:
        raw = self.fields.get("allowed_paths", "")
        if "未確定" in raw or "未定" in raw:
            # An undecided scope is not an open scope.
            return []
        return [part.strip() for part in raw.split(",") if part.strip()]

    @property
    def actionable(self) -> bool:
        """True when the controller may still spend an attempt on this job."""
        return (
            self.status in {"todo", "doing"}
            and self.attempts < ATTEMPT_LIMIT
            and bool(self.allowed_paths)
            and bool(self.test_command)
        )

    def section(self, heading: str) -> str:
        """Return the body of a `## heading` section, or an empty string."""
        pattern = re.compile(
            rf"^##\s+{re.escape(heading)}\s*$(.*?)(?=^##\s+|\Z)",
            re.MULTILINE | re.DOTALL,
        )
        found = pattern.search(self.body)
        return found.group(1).strip() if found else ""


@dataclass
class Phase:
    """A phase directory: its summary file and the jobs under it."""

    directory: Path
    tasks: list[Task] = field(default_factory=list)

    @property
    def slug(self) -> str:
        return self.directory.name

    @property
    def progress_file(self) -> Path:
        return self.directory / "PROGRESS.md"

    @property
    def decisions_file(self) -> Path:
        return self.directory / "OWNER_DECISIONS.md"

    @property
    def open_decisions(self) -> list[str]:
        """Headings of the decision requests the owner has not answered yet.

        The file keeps every request, answered or not, because the answer is the
        record of why the code looks the way it does. "The file exists" therefore
        says nothing about whether the phase is still waiting: only an entry with
        no `**Answer**` does.
        """
        if not self.decisions_file.is_file():
            return []
        text = self.decisions_file.read_bytes().decode("utf-8").replace("\r\n", "\n")
        entries = re.split(r"^##\s+", text, flags=re.MULTILINE)[1:]
        return [
            entry.split("\n", 1)[0].strip()
            for entry in entries
            if "**Question**" in entry and "**Answer**" not in entry
        ]


def parse(path: Path) -> Task:
    # Read bytes: `read_text` translates CRLF to LF, which would hide the file's
    # real line endings and make every controller edit rewrite the whole file.
    text = path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        raise TaskFormatError(f"{path}: the first line must be '---'")
    fields: dict[str, str] = {}
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            body = "\n".join(lines[index + 1 :])
            missing = {"id", "phase", "status", "attempts"} - fields.keys()
            if missing:
                raise TaskFormatError(f"{path}: missing {sorted(missing)}")
            if fields["status"] not in STATUSES:
                raise TaskFormatError(f"{path}: unknown status {fields['status']!r}")
            return Task(path=path, fields=fields, body=body, newline=newline)
        found = FIELD.match(line)
        if not found:
            raise TaskFormatError(f"{path}: {line!r} is not a single-line scalar field")
        fields[found.group(1)] = found.group(2).strip()
    raise TaskFormatError(f"{path}: the frontmatter block is not closed")


def load_phase(directory: Path) -> Phase:
    tasks = sorted(
        (parse(path) for path in (directory / "tasks").glob("*.md")),
        key=lambda task: task.id,
    )
    return Phase(directory=directory, tasks=tasks)


def update_fields(path: Path, updates: dict[str, str], *, timestamp: str) -> Task:
    """Rewrite frontmatter fields in place, always refreshing `updated`.

    Unknown keys are appended after the existing fields so a controller can add
    `reviewer` or `allowed_paths` without reordering a worker's file.
    """
    task = parse(path)
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    lines = text.split("\n")
    close = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    wanted = {**updates, "updated": timestamp}
    if "status" in wanted and wanted["status"] not in STATUSES:
        raise TaskFormatError(f"{path}: refusing unknown status {wanted['status']!r}")
    for index in range(1, close):
        found = FIELD.match(lines[index])
        if found and found.group(1) in wanted:
            lines[index] = f"{found.group(1)}: {wanted.pop(found.group(1))}"
    for key in list(wanted):
        lines.insert(close, f"{key}: {wanted.pop(key)}")
        close += 1
    path.write_text(task.newline.join(lines), encoding="utf-8", newline="")
    return parse(path)


def append_section(path: Path, heading: str, body: str) -> None:
    """Append a new `## heading` section, leaving existing sections untouched."""
    task = parse(path)
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").rstrip("\n")
    block = f"\n\n## {heading}\n\n{body.strip()}\n"
    path.write_text(
        (text + block).replace("\n", task.newline),
        encoding="utf-8",
        newline="",
    )
