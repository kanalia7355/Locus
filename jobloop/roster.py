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
from typing import Any

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
# A containment stop means the worker wrote product code into the main checkout
# instead of its workspace. One stop is not enough to blame the model: the
# orchestrator's own edits have caused them before (2026-11-20, 2026-11-22). The
# rate is measured over dispatches, not over `observations`, because observations
# count every rest event and a dispatch count is what the denominator means.
CONTAINMENT_MIN_DISPATCHES = 5
CONTAINMENT_RATE = 0.5

_LATEST_CONTAINMENT_REPORT = ""
_LAST_PROGRESS_PATH: Path | None = None


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
        changed = False
        for name in self.models:
            entry = spent.get(name, {})
            dispatches = int(entry.get("dispatches", 0))
            stops = int(entry.get("containment_stops", 0))
            if (
                dispatches >= CONTAINMENT_MIN_DISPATCHES
                and stops >= CONTAINMENT_RATE * dispatches
                and float(entry.get("cooldown_until", 0)) <= self.now
                and not entry.get("containment_rested")
            ):
                entry = spent.setdefault(name, {})
                entry["cooldown_until"] = self.now + COOLDOWN_SECONDS
                entry["observations"] = float(entry.get("observations", 0)) + 1
                entry["containment_rested"] = 1.0
                entry["containment_rested_dispatches"] = float(dispatches)
                entry["containment_rested_stops"] = float(stops)
                changed = True
        if changed:
            self._save(spent)
        return [
            name
            for name in self.models
            if name not in exclude and not self._cooled_down(spent.get(name, {}))
        ]

    def _cooled_down(self, entry: dict[str, float]) -> bool:
        return float(entry.get("cooldown_until", 0)) > self.now

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

    def mark_dispatched(self, model: str) -> None:
        """Count one dispatch. Distinct from observations: this is the denominator
        for containment rate, and mixing it with rest counts would make the rate
        meaningless."""
        state = self._state()
        entry = state.setdefault(model, {})
        entry["dispatches"] = float(entry.get("dispatches", 0)) + 1
        self._save(state)

    def containment_stats(self, model: str) -> tuple[int, int]:
        """Return (dispatches, containment_stops) for a model."""
        entry = self._state().get(model, {})
        return int(entry.get("dispatches", 0)), int(entry.get("containment_stops", 0))

    def mark_containment_stop(self, model: str, *, orchestrator_busy: bool) -> dict[str, object]:
        """Record a containment stop and rest the model when its rate crosses the
        threshold.

        A stop whose evidence says `marker=... present=True` came from the
        orchestrator's own edit, not the model. It is never counted in the
        numerator. The containment judgement itself is the caller's responsibility;
        this method only measures and, when the rate is high enough, cools the model
        down through the same COOLDOWN_SECONDS mechanism as usage exhaustion.
        """
        state = self._state()
        entry = state.setdefault(model, {})
        dispatches = int(entry.get("dispatches", 0))
        stops = int(entry.get("containment_stops", 0))
        counted = not orchestrator_busy
        if counted:
            stops += 1
            entry["containment_stops"] = float(stops)
        already_rested = bool(entry.get("containment_rested"))
        rested = False
        if (
            counted
            and dispatches >= CONTAINMENT_MIN_DISPATCHES
            and stops >= CONTAINMENT_RATE * dispatches
        ):
            entry["cooldown_until"] = self.now + COOLDOWN_SECONDS
            if not already_rested:
                entry["observations"] = float(entry.get("observations", 0)) + 1
            entry["containment_rested"] = 1.0
            entry["containment_rested_dispatches"] = float(dispatches)
            entry["containment_rested_stops"] = float(stops)
            rested = True
        self._save(state)
        self._save(state)
        report = {
            "model": model,
            "dispatches": dispatches,
            "containment_stops": stops,
            "counted": counted,
            "rested": rested,
        }
        self._update_containment_report(state)
        return report

    def containment_summary(self) -> str:
        """Human-readable containment/dispatch stats for logs and diagnose output."""
        return _containment_summary_from_state(self._state())

    def _update_containment_report(self, state: dict[str, dict[str, float]]) -> None:
        global _LATEST_CONTAINMENT_REPORT
        _LATEST_CONTAINMENT_REPORT = _containment_summary_from_state(state)

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
        self._update_containment_report(state)


def _containment_summary_from_state(state: dict[str, dict[str, float]]) -> str:
    lines: list[str] = []
    for model in sorted(state):
        entry = state.get(model, {})
        dispatches = int(entry.get("dispatches", 0))
        stops = int(entry.get("containment_stops", 0))
        rested = bool(entry.get("containment_rested"))
        if dispatches == 0 and stops == 0 and not rested:
            continue
        status = " rested" if rested else ""
        lines.append(f"containment {model}: {stops}/{dispatches} stops/dispatches{status}")
    return "\n".join(lines)


def containment_report() -> str:
    return _LATEST_CONTAINMENT_REPORT


def _containment_report_from_disk() -> str:
    candidates: list[Path] = []
    if _LAST_PROGRESS_PATH is not None:
        candidates.append(_LAST_PROGRESS_PATH.parent / ".jobloop" / "roster.json")
    candidates.append(Path.cwd() / ".jobloop" / "roster.json")
    for path in candidates:
        if not path.is_file():
            continue
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(loaded, dict):
            return _containment_summary_from_state(loaded)
    return ""


def _patch_diagnose_report() -> None:
    try:
        from jobloop import diagnose
    except Exception:
        return

    original_report = getattr(diagnose, "report", None)
    original_survey = getattr(diagnose, "survey", None)
    if original_report is None or getattr(original_report, "_containment_patched", False):
        return

    if original_survey is not None and not getattr(original_survey, "_containment_patched", False):

        def survey(progress: Path, phases: list[str]) -> list[Any]:
            global _LAST_PROGRESS_PATH
            _LAST_PROGRESS_PATH = Path(progress)
            return original_survey(progress, phases)

        survey._containment_patched = True  # type: ignore[attr-defined]
        diagnose.survey = survey

    def report(findings: list[Any]) -> str:
        base = original_report(findings)
        extra = containment_report()
        if not extra:
            extra = _containment_report_from_disk()
        if not extra:
            return base
        return base + "\n" + extra

    report._containment_patched = True  # type: ignore[attr-defined]
    diagnose.report = report


_patch_diagnose_report()
