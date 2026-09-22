"""
Honest unavailable-state browser adapter (RSR-01b, ARCH-11-005..009).

The Playwright browser worker deploys with RSR-01c (task 28). Until then the
typed ``BrowserSessionPort`` answers every call with a typed refusal naming
the missing dependency - the executor records that refusal as evidence and
the run continues/finishes honestly instead of silently skipping.
"""

from __future__ import annotations

from milpbooklm_application.research_browser import (
    BrowserErrorCode,
    BrowserGestureCommand,
    BrowserObservation,
    BrowserPage,
    BrowserUnavailableError,
)

_DETAIL = "browser worker deploys with RSR-01c (task 28); no browser tool can run yet"


class UnavailableBrowserSession:
    """Every browser tool call refuses with the explicit not-deployed state."""

    async def open(self, url: str) -> BrowserPage:
        """Refuse: no browser worker is deployed."""
        raise BrowserUnavailableError(BrowserErrorCode.WORKER_NOT_DEPLOYED, _DETAIL)

    async def observe(self, focus: str | None = None) -> BrowserObservation:
        """Refuse: no browser worker is deployed."""
        raise BrowserUnavailableError(BrowserErrorCode.WORKER_NOT_DEPLOYED, _DETAIL)

    async def interact(self, command: BrowserGestureCommand) -> BrowserObservation:
        """Refuse: no browser worker is deployed."""
        del command
        raise BrowserUnavailableError(BrowserErrorCode.WORKER_NOT_DEPLOYED, _DETAIL)
