"""
Research run state machine and tool surface (RSR-01b, guide/11, ARCH-11-001..012).

A research run is a durable state machine DISTINCT from chat: it begins from an
immutable snapshot of its initial inputs, executes planning/model steps and
constrained tool calls, and appends immutable evidence per tool output. The
tool surface is EXACTLY the seven constrained tools below - no arbitrary
Playwright/eval APIs exist in the vocabulary, so nothing outside it can be
selected, proposed, or granted (server-side authorization re-checks every
call; model output never grants capability).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class ResearchRunStatus(StrEnum):
    """Durable research run states (created -> running -> paused -> terminal)."""

    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_RUN_STATES: frozenset[ResearchRunStatus] = frozenset(
    {ResearchRunStatus.SUCCEEDED, ResearchRunStatus.FAILED, ResearchRunStatus.CANCELLED}
)

# Compare-and-swap transition table: a run moves only along these edges.
RUN_TRANSITIONS: Final[dict[ResearchRunStatus, frozenset[ResearchRunStatus]]] = {
    ResearchRunStatus.CREATED: frozenset({ResearchRunStatus.RUNNING, ResearchRunStatus.CANCELLED}),
    ResearchRunStatus.RUNNING: frozenset(
        {
            ResearchRunStatus.PAUSED,
            ResearchRunStatus.SUCCEEDED,
            ResearchRunStatus.FAILED,
            ResearchRunStatus.CANCELLED,
        }
    ),
    # Paused is resumable: the durable step/evidence trace survives and the
    # run re-enters running without re-running completed side effects.
    ResearchRunStatus.PAUSED: frozenset({ResearchRunStatus.RUNNING, ResearchRunStatus.CANCELLED}),
    ResearchRunStatus.SUCCEEDED: frozenset(),
    ResearchRunStatus.FAILED: frozenset(),
    ResearchRunStatus.CANCELLED: frozenset(),
}


class IllegalRunTransitionError(ValueError):
    """A run transition outside the CAS table (stale writer, double-terminal)."""


def run_transition_allowed(current: ResearchRunStatus, target: ResearchRunStatus) -> bool:
    """Return True when current -> target is a legal run state edge."""
    return target in RUN_TRANSITIONS[current]


class RunMode(StrEnum):
    """Explicit research modes (distinct capabilities, guide Table B)."""

    SOURCE_DISCOVERY = "source_discovery"
    DEEP_RESEARCH = "deep_research"


class ResearchTool(StrEnum):
    """The constrained research tool surface - EXACTLY seven tools (guide/11)."""

    WEB_SEARCH = "web.search"
    WEB_FETCH = "web.fetch"
    BROWSER_OPEN = "browser.open"
    BROWSER_OBSERVE = "browser.observe"
    BROWSER_INTERACT = "browser.interact"
    SOURCE_IMPORT = "source.import"
    NOTEBOOK_RETRIEVE = "notebook.retrieve"


RESEARCH_TOOL_SURFACE: frozenset[str] = frozenset(tool.value for tool in ResearchTool)

# Side-effecting tools require an explicit capability + approval recorded on
# the run before the executor will dispatch them (server-side enforcement).
SIDE_EFFECT_TOOLS: frozenset[str] = frozenset(
    {ResearchTool.SOURCE_IMPORT.value, ResearchTool.BROWSER_INTERACT.value}
)

MAX_RESEARCH_STEPS: Final = 64
MAX_RESEARCH_TOOL_CALLS: Final = 48
MAX_RESEARCH_IMPORTS: Final = 8


@dataclass(frozen=True, slots=True)
class ResearchBudget:
    """Explicit per-run budget: step, tool-call, and import ceilings."""

    max_steps: int = MAX_RESEARCH_STEPS
    max_tool_calls: int = MAX_RESEARCH_TOOL_CALLS
    max_imports: int = MAX_RESEARCH_IMPORTS

    def __post_init__(self) -> None:
        """Reject non-positive or above-global-ceiling budgets."""
        if self.max_steps < 1 or self.max_steps > MAX_RESEARCH_STEPS:
            raise ValueError(f"max_steps must be within 1..{MAX_RESEARCH_STEPS}")
        if self.max_tool_calls < 1 or self.max_tool_calls > MAX_RESEARCH_TOOL_CALLS:
            raise ValueError(f"max_tool_calls must be within 1..{MAX_RESEARCH_TOOL_CALLS}")
        if self.max_imports < 0 or self.max_imports > MAX_RESEARCH_IMPORTS:
            raise ValueError(f"max_imports must be within 0..{MAX_RESEARCH_IMPORTS}")
