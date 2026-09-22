"""
Browser tool ports for the research runtime (RSR-01b, ARCH-11-005..009).

Typed, constrained surface only: open/observe/interact with structured
observations. There is deliberately NO evaluate/eval/execute-shaped method -
arbitrary script execution is not part of the vocabulary a model can select.
The worker-side Playwright implementation lands with RSR-01c (task 28); until
then the honest adapter answers every call with a typed
``BrowserUnavailableError`` refusal that the executor records as evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class BrowserErrorCode:
    """Stable browser tool refusal classes."""

    WORKER_NOT_DEPLOYED = "browser_worker_not_deployed"
    UNSUPPORTED = "unsupported"


class BrowserUnavailableError(Exception):
    """
    A browser tool call was refused: no browser worker is deployed.

    Hand-written (no dataclass machinery): the refusal crosses async
    deadline scopes during unwinding (T26 lesson).
    """

    __slots__ = ("code", "detail")

    def __init__(self, code: str, detail: str) -> None:
        """Bind the stable refusal code and safe detail."""
        super().__init__(code, detail)
        self.code = code
        self.detail = detail

    def __str__(self) -> str:
        """Return the stable code and safe detail."""
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True, slots=True)
class BrowserPage:
    """Structured open() result (no raw DOM, no scripts)."""

    url: str
    title: str
    text_excerpt: str


@dataclass(frozen=True, slots=True)
class BrowserObservation:
    """Structured observe()/interact() result."""

    url: str
    title: str
    visible_text_excerpt: str
    focused_excerpt: str | None = None


@dataclass(frozen=True, slots=True)
class BrowserGestureCommand:
    """One constrained gesture (mirrors BrowserInteractAction)."""

    gesture: str
    selector: str
    value: str | None = None


class BrowserSessionPort(Protocol):
    """The disposable browser context a research run may use."""

    async def open(self, url: str) -> BrowserPage:
        """Navigate the run's context to one URL (SSRF policy applies)."""
        ...

    async def observe(self, focus: str | None = None) -> BrowserObservation:
        """Read a structured observation of the current page."""
        ...

    async def interact(self, command: BrowserGestureCommand) -> BrowserObservation:
        """Apply one constrained gesture (side effect; approval-checked)."""
        ...
