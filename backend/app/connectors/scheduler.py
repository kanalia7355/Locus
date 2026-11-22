"""Scheduler control for original-source sync cycles."""

from __future__ import annotations

import time
from collections.abc import Callable

DEFAULT_INTERVAL_SECONDS = 600


class SourceScheduler:
    """Interval-driven source sync control with an injectable clock and notifications."""

    def __init__(
        self,
        interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.interval_seconds = interval_seconds
        self._clock = clock or time.monotonic
        self._last_run: dict[str, float] = {}
        self._pending: set[str] = set()

    def _now(self) -> float:
        return self._clock()

    def should_run(self, source_id: str, now: float | None = None) -> bool:
        """True when the source is due; a notification forces an immediate run."""
        current = self._clock() if now is None else now
        if source_id in self._pending:
            return True
        last_run = self._last_run.get(source_id)
        if last_run is None:
            return True
        return (current - last_run) >= self.interval_seconds

    def mark_run(self, source_id: str, now: float | None = None) -> None:
        self._pending.discard(source_id)
        self._last_run[source_id] = self._clock() if now is None else now

    def notify(self, source_id: str) -> None:
        """Request an immediate recheck for one source without waiting for the interval."""
        self._pending.add(source_id)
