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
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, SupportsFloat, SupportsIndex, cast

# Only providers that answer at no cost are eligible. `opencode/*-free` is the
# documented free tier; `ollama/*` runs locally. Paid `openai/*` routes stay out
# of the roster so a loop cannot silently spend money.
FREE_SUFFIX = "-free"
FREE_PREFIXES = ("opencode/",)
LOCAL_PREFIXES = ("ollama/",)
# Second tier, used only once every first-tier model is cooled down. The owner
# granted it on 2026-11-25 (E2 in `docs/plans/OWNER_DECISIONS_2026-11-25-ENTRIES.md`)
# after the free tier was wholly spent for about six hours and nothing could run:
# the reviewer is drawn from this same roster, so an exhausted first tier stops
# review as well as implementation.
#
# The owner named three families and a role for each. Nothing else `agy models`
# reports is eligible — not `gemini-4-neon-*`, not the Claude or GPT entries —
# because a model the owner did not assign is a model nobody chose.
AGY_PREFIX = "agy/"
AGY_ROLES = {
    "implement": "agy/gemini-4-carbon-",
    "review": "agy/gemini-4-argon-",
    "light": "agy/gemini-4-hydrogen-",
}
# Within one family, try the cheaper reasoning effort first and keep the costlier
# ones as the fallback, so a spent allowance is not spent faster than it has to be.
AGY_EFFORT_ORDER = ("-low", "-medium", "-high", "-xhigh")
# Capability order for implementation work, best first. Unlisted eligible models
# keep their CLI order after these, so a new free model is usable immediately but
# never outranks a model we have evidence for.
PREFERRED = (
    "opencode/deepseek-v4.1-flash-free",
    "opencode/iceman-free",
    "opencode/flint-40b-free",
    "opencode/nemotron-3.5-lightning-free",
    "opencode/beam-free",
    "opencode/mimo-v2.6-flash-free",
    "opencode/nemotron-3.5-super-vl-free",
)
COOLDOWN_SECONDS = 6 * 60 * 60
# If a model answers "out of usage" again within this window after its previous
# cooldown expired, the allowance had not actually reset; double the next rest
# up to EXHAUSTION_COOLDOWN_CAP so every provider is still tried at least daily.
EXHAUSTION_RETRY_WINDOW_SECONDS = 30 * 60
EXHAUSTION_COOLDOWN_CAP = 24 * 60 * 60
# A containment stop means the worker wrote product code into the main checkout
# instead of its workspace. One stop is not enough to blame the model: the
# orchestrator's own edits have caused them before (2026-11-20, 2026-11-22). The
# rate is measured over dispatches, not over `observations`, because observations
# count every rest event and a dispatch count is what the denominator means.
CONTAINMENT_MIN_DISPATCHES = 5
CONTAINMENT_RATE = 0.5

_LATEST_CONTAINMENT_REPORT = ""
_LAST_PROGRESS_PATH: Path | None = None


def agy_role(name: str) -> str | None:
    """Which assigned role an `agy/` identifier fills, or None if unassigned."""
    for role, prefix in AGY_ROLES.items():
        if name.startswith(prefix):
            return role
    return None


def _agy_rank(name: str) -> tuple[int, int, str]:
    """Order agy ids by role, then by reasoning effort, cheapest first."""
    roles = list(AGY_ROLES)
    role = agy_role(name)
    effort = next(
        (i for i, suffix in enumerate(AGY_EFFORT_ORDER) if name.endswith(suffix)),
        len(AGY_EFFORT_ORDER),
    )
    return (roles.index(role) if role in roles else len(roles), effort, name)


def eligible(identifiers: list[str]) -> list[str]:
    """Keep the usable identifiers, first tier first, best-known capability first.

    The order is the whole fallback policy: every free and local model comes
    before every `agy/` one, so the second tier is reached only when `available()`
    has cooled all of the first tier down. Nothing here spends money — `agy/` is
    the owner's own subscription, granted for exactly this case.
    """
    free = [
        name
        for name in identifiers
        if (name.startswith(FREE_PREFIXES) and name.endswith(FREE_SUFFIX))
        or name.startswith(LOCAL_PREFIXES)
    ]
    ranked = [name for name in PREFERRED if name in free]
    first = ranked + [name for name in free if name not in ranked]
    second = sorted(
        (
            name
            for name in identifiers
            if name.startswith(AGY_PREFIX) and agy_role(name) is not None
        ),
        key=_agy_rank,
    )
    return first + second


def preferred_divergence(identifiers: list[str]) -> tuple[list[str], list[str]]:
    """Return (missing_from_provided, unlisted_free) between PREFERRED and identifiers.

    Pure function with no side effects: does not read or write roster.json.
    """
    free = [
        name
        for name in identifiers
        if (name.startswith(FREE_PREFIXES) and name.endswith(FREE_SUFFIX))
        or name.startswith(LOCAL_PREFIXES)
    ]
    free_set = set(free)
    preferred_set = set(PREFERRED)
    missing = [name for name in PREFERRED if name not in free_set]
    unlisted = [name for name in free if name not in preferred_set]
    return missing, unlisted


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
        except Exception as exc:
            # An unreadable roster must not kill the whole loop; record and treat as empty.
            print(f"roster unreadable: {self.state_file}: {exc}", file=sys.stderr)
            return {}
        if not isinstance(loaded, dict):
            return {}
        return cast(dict[str, dict[str, float]], loaded)

    def _entry_for_write(self, state: dict[str, Any], model: str) -> dict[str, float]:
        existing = state.get(model)
        if isinstance(existing, dict):
            return existing
        fresh: dict[str, float] = {}
        state[model] = fresh
        return fresh

    def available(self, *, exclude: tuple[str, ...] = ()) -> list[str]:
        spent = self._state()
        changed = False
        for name in self.models:
            entry = spent.get(name, {})
            if not isinstance(entry, dict):
                continue
            dispatches = _finite_int(entry.get("dispatches", 0))
            stops = _finite_int(entry.get("containment_stops", 0))
            until = _finite_float(entry.get("cooldown_until", 0))
            if dispatches is None or stops is None or until is None:
                continue
            if (
                dispatches >= CONTAINMENT_MIN_DISPATCHES
                and stops >= CONTAINMENT_RATE * dispatches
                and until <= self.now
                and not entry.get("containment_rested")
            ):
                entry["cooldown_until"] = self.now + COOLDOWN_SECONDS
                entry["observations"] = (_finite_float(entry.get("observations", 0)) or 0.0) + 1
                entry["containment_rested"] = 1.0
                entry["containment_rested_dispatches"] = float(dispatches)
                entry["containment_rested_stops"] = float(stops)
                changed = True
        if changed:
            self._save(spent)
        return [
            name
            for name in self.models
            if name not in exclude
            and not self._cooled_down(spent.get(name, {}))
            and not spent.get(name, {}).get("tool_incompatible")
        ]

    def _cooled_down(self, entry: object) -> bool:
        if not isinstance(entry, dict):
            return True
        until = _finite_float(entry.get("cooldown_until", 0))
        if until is None:
            return True
        return until > self.now

    def pick(self, *, exclude: tuple[str, ...] = (), role: str = "implement") -> str | None:
        """The best eligible model that is not excluded and not on cooldown.

        `role` only narrows the second tier, where the owner assigned one family
        per role (2026-11-25, E2): Carbon implements, Argon reviews, Hydrogen takes
        the light work. First-tier free models carry no role, so they are offered
        for any role and still come first. An `agy/` model whose role is not the
        one being asked for is skipped rather than substituted — handing a review
        to the implementing family is the thing the assignment exists to prevent.
        """
        wanted = role if role in AGY_ROLES else "implement"
        candidates = self.available(exclude=exclude)
        for name in candidates:
            if not name.startswith(AGY_PREFIX) or agy_role(name) == wanted:
                return name
        # The assignment is a preference, not a prohibition. The owner assigned
        # roles so that work gets done, so a spent Hydrogen must not make a light
        # job report `no-model` while Carbon sits there available — that would
        # stall the queue in the name of a preference. Review keeps its real
        # guarantee either way: `exclude` already holds the implementer out, which
        # is the constraint that matters (CONSTRAINTS §5-5).
        return candidates[0] if candidates else None

    def pick_reviewer(self, implementer: str) -> str | None:
        """A reviewer must not be the model that wrote the code (CONSTRAINTS §5-5).

        Models the CLI cannot run at all (tool-incompatible) are excluded from
        the reviewer candidate list, independently of the implementer exclusion.
        """
        return self.pick(exclude=(implementer,), role="review")

    def mark_exhausted(self, model: str, *, seconds: float = COOLDOWN_SECONDS) -> float:
        """Rest a spent model, doubling when re-exhausted right after cooldown.

        When a model answers "out of usage" again within
        `EXHAUSTION_RETRY_WINDOW_SECONDS` of its previous `cooldown_until`, its
        allowance has not reset yet; double the cooldown as `mark_unavailable`
        does, capped at `EXHAUSTION_COOLDOWN_CAP` so it is still tried at least
        once a day. Exhaustion after a longer run is normal consumption and
        resets the streak to 1.
        """
        state = self._state()
        entry = self._entry_for_write(state, model)
        prev_until = _finite_float(entry.get("cooldown_until"))
        prev_streak = _finite_float(entry.get("exhausted_streak", 0)) or 0.0
        if (
            prev_until is not None
            and prev_until > 0
            and prev_streak >= 1.0
            and self.now <= prev_until + EXHAUSTION_RETRY_WINDOW_SECONDS
        ):
            streak = prev_streak + 1.0
        else:
            streak = 1.0
        entry["exhausted_streak"] = streak
        steps = min(streak - 1.0, 16.0)
        rest = float(min(seconds * (2.0**steps), max(seconds, EXHAUSTION_COOLDOWN_CAP)))
        entry["cooldown_until"] = self.now + rest
        entry["observations"] = (_finite_float(entry.get("observations", 0)) or 0.0) + 1
        self._save(state)
        return rest

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
        entry = self._entry_for_write(state, model)
        # Counted separately from `observations`, which keeps its existing
        # meaning: every rest, exhaustion and unavailability alike, so old
        # records stay readable as what they are.
        streak = (_finite_float(entry.get("unavailable_streak", 0)) or 0.0) + 1
        entry["unavailable_streak"] = streak
        # Clamped: the streak is unbounded, since a dead provider is picked
        # again every six hours, and `2.0 ** 1460` would raise rather than rest.
        steps = min(streak - 1, 16)
        seconds = float(min(base_seconds * (2.0**steps), COOLDOWN_SECONDS))
        entry["cooldown_until"] = self.now + seconds
        entry["observations"] = (_finite_float(entry.get("observations", 0)) or 0.0) + 1
        self._save(state)
        return seconds

    def mark_tool_incompatible(self, model: str) -> None:
        """Exclude a model that does not support tool calls.

        Unlike `mark_unavailable`, this does not set a cooldown: an
        incompatible model is not temporarily resting and will not come back
        later. Persisting the flag in state ensures `available()`, `pick()`,
        `pick_reviewer()`, and `shift_check` all exclude it across restarts.
        """
        state = self._state()
        entry = self._entry_for_write(state, model)
        entry["tool_incompatible"] = 1.0
        self._save(state)

    def mark_dispatched(self, model: str) -> None:
        """Count one dispatch. Distinct from observations: this is the denominator
        for containment rate, and mixing it with rest counts would make the rate
        meaningless."""
        state = self._state()
        entry = self._entry_for_write(state, model)
        entry["dispatches"] = (_finite_float(entry.get("dispatches", 0)) or 0.0) + 1
        self._save(state)

    def containment_stats(self, model: str) -> tuple[int, int]:
        """Return (dispatches, containment_stops) for a model."""
        entry = self._state().get(model, {})
        if not isinstance(entry, dict):
            return 0, 0
        return (
            _finite_int(entry.get("dispatches", 0)) or 0,
            _finite_int(entry.get("containment_stops", 0)) or 0,
        )

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
        entry = self._entry_for_write(state, model)
        dispatches = _finite_int(entry.get("dispatches", 0)) or 0
        stops = _finite_int(entry.get("containment_stops", 0)) or 0
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
                entry["observations"] = (_finite_float(entry.get("observations", 0)) or 0.0) + 1
            entry["containment_rested"] = 1.0
            entry["containment_rested_dispatches"] = float(dispatches)
            entry["containment_rested_stops"] = float(stops)
            rested = True
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
        """Forget failure and exhaustion streaks: the model just answered a job.

        Without this the streaks would describe the model's whole history, and a
        model that had one bad afternoon or a long quota cycle would keep resting
        for the stretched duration even after recovering. The controller calls it
        on the reply paths it already has, for the implementer and for the reviewer.
        """
        state = self._state()
        entry = state.get(model)
        if not isinstance(entry, dict):
            return
        has_unavailable = bool(_finite_float(entry.get("unavailable_streak", 0)))
        has_exhausted = bool(_finite_float(entry.get("exhausted_streak", 0)))
        if not has_unavailable and not has_exhausted:
            return
        if has_unavailable:
            entry["unavailable_streak"] = 0
        if has_exhausted:
            entry["exhausted_streak"] = 0
        self._save(state)

    def _save(self, state: dict[str, dict[str, float]]) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(
            json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        self._update_containment_report(state)


def _finite_float(value: object) -> float | None:
    if not isinstance(value, (int, float, str, bytes, bytearray, SupportsFloat, SupportsIndex)):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _finite_int(value: object) -> int | None:
    parsed = _finite_float(value)
    return int(parsed) if parsed is not None else None


def _containment_summary_from_state(state: dict[str, dict[str, float]]) -> str:
    lines: list[str] = []
    for model in sorted(state):
        entry = state.get(model, {})
        if not isinstance(entry, dict):
            continue
        dispatches = _finite_int(entry.get("dispatches", 0)) or 0
        stops = _finite_int(entry.get("containment_stops", 0)) or 0
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
        except Exception as exc:
            print(f"roster unreadable: {path}: {exc}", file=sys.stderr)
            continue
        if isinstance(loaded, dict):
            state = cast(dict[str, dict[str, float]], loaded)
            return _containment_summary_from_state(state)
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
            surveyed: list[Any] = list(original_survey(progress, phases))
            return surveyed

        survey._containment_patched = True  # type: ignore[attr-defined]
        diagnose.survey = survey

    def report(findings: list[Any]) -> str:
        base: str = str(original_report(findings))
        extra = containment_report()
        if not extra:
            extra = _containment_report_from_disk()
        if not extra:
            return base
        return base + "\n" + extra

    report._containment_patched = True  # type: ignore[attr-defined]
    diagnose.report = report


_patch_diagnose_report()
