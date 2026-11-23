"""Choose which free model runs a job, and remember which ones are spent.

Usage exhaustion is not a model failure (`docs/agent/PROTOCOL.md` §5.4), so an
exhausted model is put on cooldown and the next eligible one takes the job
without consuming the task's attempt budget. A model the CLI could not run at
all is rested too, and that rest grows while the failure repeats: one outage is
a wait, the seventeenth is a broken provider. Model identifiers are never
guessed: the roster is the intersection of this file's eligibility rules and the
identifiers the installed CLI actually reports.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# Only providers that answer at no cost are eligible. `opencode/*-free` is the
# documented free tier; `ollama/*` runs locally. Paid `openai/*` routes stay out
# of the roster so a loop cannot silently spend money.
FREE_SUFFIX = "-free"
FREE_PREFIXES = ("opencode/",)
LOCAL_PREFIXES = ("ollama/",)
# Capability order for implementation work, best first. Unlisted eligible models
# keep their CLI order after these, so a new free model is usable immediately but
# never outranks a model we have evidence for.
PREFERRED = (
    "opencode/glm-5.3-flash-free",
    "opencode/deepseek-v4.1-flash-free",
    "opencode/minimax-m3.1-flash-free",
    "opencode/longcat-2.5-free",
    "opencode/flint-40b-free",
    "opencode/mimo-v2.6-flash-free",
    "opencode/nemotron-3.5-super-vl-free",
    "opencode/nemotron-3.5-lightning-free",
    "opencode/inkling-2-small-free",
    "opencode/iceman-free",
    "opencode/beam-free",
)
COOLDOWN_SECONDS = 6 * 60 * 60


def eligible(identifiers: list[str]) -> list[str]:
    """Keep the free and local identifiers, best-known capability first."""
    free = [
        name
        for name in identifiers
        if (name.startswith(FREE_PREFIXES) and name.endswith(FREE_SUFFIX))
        or name.startswith(LOCAL_PREFIXES)
    ]
    ranked = [name for name in PREFERRED if name in free]
    return ranked + [name for name in free if name not in ranked]


@dataclass
class Roster:
    """Eligible models plus the persisted record of which ones are spent."""

    models: list[str]
    state_file: Path
    now: float

    def _state(self) -> dict[str, dict[str, float]]:
        if not self.state_file.is_file():
            return {}
        try:
            loaded = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return loaded if isinstance(loaded, dict) else {}

    def available(self, *, exclude: tuple[str, ...] = ()) -> list[str]:
        spent = self._state()
        return [
            name
            for name in self.models
            if name not in exclude and spent.get(name, {}).get("cooldown_until", 0) <= self.now
        ]

    def pick(self, *, exclude: tuple[str, ...] = ()) -> str | None:
        """The best eligible model that is not excluded and not on cooldown."""
        candidates = self.available(exclude=exclude)
        return candidates[0] if candidates else None

    def pick_reviewer(self, implementer: str) -> str | None:
        """A reviewer must not be the model that wrote the code (CONSTRAINTS §5-5)."""
        return self.pick(exclude=(implementer,))

    def mark_exhausted(self, model: str, *, seconds: float = COOLDOWN_SECONDS) -> None:
        state = self._state()
        entry = state.setdefault(model, {})
        entry["cooldown_until"] = self.now + seconds
        entry["observations"] = float(entry.get("observations", 0)) + 1
        self._save(state)

    def mark_unavailable(self, model: str, *, base_seconds: float) -> float:
        """Rest a model the CLI could not run, twice as long for each repeat.

        `base_seconds` is the caller's judgement for a single failure (short for
        an outage, the exhaustion period for a provider that said outright it
        cannot do the work). The judgement that is missing from a fixed value is
        **repetition**: a provider that fails for a new reason every time never
        matches a known string, so on 2026-11-22 the roster picked it up again
        every fifteen minutes — `ollama/gemma3:4b` reached 17 observations, the
        highest in the file, and would have gone on doing so for ever. Counting
        matches no reason, so a reason nobody has seen yet is covered too.

        It is capped at `COOLDOWN_SECONDS` rather than removing the model: a
        dead provider is still tried four times a day, and one that recovers is
        back the moment it answers.

        Returns the seconds it was rested for, so the caller can record it.
        """
        state = self._state()
        entry = state.setdefault(model, {})
        # Counted separately from `observations`, which keeps its existing
        # meaning: every rest, exhaustion and unavailability alike, so old
        # records stay readable as what they are.
        streak = float(entry.get("unavailable_streak", 0)) + 1
        entry["unavailable_streak"] = streak
        # Clamped: the streak is unbounded, since a dead provider is picked
        # again every six hours, and `2.0 ** 1460` would raise rather than rest.
        steps = min(streak - 1, 16)
        seconds = min(base_seconds * 2.0**steps, COOLDOWN_SECONDS)
        entry["cooldown_until"] = self.now + seconds
        entry["observations"] = float(entry.get("observations", 0)) + 1
        self._save(state)
        return seconds

    def mark_responded(self, model: str) -> None:
        """Forget the failure streak: the model just answered a job.

        Without this the streak would describe the model's whole history, and a
        model that had one bad afternoon would rest six hours at a time for the
        rest of the phase. The controller calls it on the reply paths it
        already has, for the implementer and for the reviewer.
        """
        state = self._state()
        entry = state.get(model)
        if not entry or not entry.get("unavailable_streak"):
            return
        entry["unavailable_streak"] = 0
        self._save(state)

    def _save(self, state: dict[str, dict[str, float]]) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(
            json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
