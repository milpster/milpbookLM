"""
In-memory provider health recording: the last observed call outcome, never a probe.

Providers own their health signal: every real call records success or failure
here, and the API's component-health surface reports the latest evidence. No
component of this module ever contacts a provider on its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from milpbooklm_application.ports import Clock

_SECONDS_PER_MINUTE = 60
_SECONDS_PER_HOUR = 3600


@dataclass(frozen=True, slots=True)
class ProviderHealthSnapshot:
    """The latest evidence about one provider (never fabricated)."""

    healthy: bool
    detail: str


@dataclass(slots=True)
class ProviderHealth:
    """Record the last success/failure timestamps of one wired provider."""

    clock: Clock
    _last_success: datetime | None = field(default=None, init=False)
    _last_failure: datetime | None = field(default=None, init=False)
    _failure_reason: str = ""

    def record_success(self) -> None:
        """Record a successful provider call."""
        self._last_success = self.clock.now()

    def record_failure(self, reason: str) -> None:
        """Record a failed provider call (reason: a short class, never a URL or body)."""
        self._last_failure = self.clock.now()
        self._failure_reason = reason

    def snapshot(self) -> ProviderHealthSnapshot:
        """Report the latest evidence: a failure after the last success degrades."""
        now = self.clock.now()
        if (
            self._last_failure is not None
            and (self._last_success is None or self._last_failure > self._last_success)
        ):
            return ProviderHealthSnapshot(False, f"last request failed ({self._failure_reason})")
        if self._last_success is not None:
            detail = f"last request succeeded {_ago(now, self._last_success)}"
            return ProviderHealthSnapshot(True, detail)
        return ProviderHealthSnapshot(False, "no traffic observed")


def _ago(now: datetime, then: datetime) -> str:
    """Human-short age for detail labels (minutes under an hour, hours above)."""
    seconds = (now - then).total_seconds()
    if seconds < _SECONDS_PER_MINUTE:
        return "just now"
    if seconds < _SECONDS_PER_HOUR:
        return f"{int(seconds // _SECONDS_PER_MINUTE)}m ago"
    return f"{int(seconds // _SECONDS_PER_HOUR)}h ago"
