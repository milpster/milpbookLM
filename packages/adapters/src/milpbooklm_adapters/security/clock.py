"""System clock adapter (UTC, timezone-aware)."""

from __future__ import annotations

from datetime import UTC, datetime


class SystemClock:
    """The production clock: the current UTC time."""

    def now(self) -> datetime:
        """Return the current UTC time (timezone-aware)."""
        return datetime.now(UTC)
