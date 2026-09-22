"""
Web search port and discovery contract (RSR-01a, guide/11 SearXNG section).

SearXNG is DISCOVERY ONLY: every hit (URL/title/snippet) is untrusted data.
Consumers must route discovered URLs through the hardened fetch service
(``web_fetch``) and normal ingestion controls; search output is never trusted
or imported directly. Because SearXNG has no independent index, coverage and
availability depend on responding upstream engines — so responses carry an
explicit outcome (``complete``/``partial``), the unresponsive engines are
recorded, and an all-degraded answer is a PARTIAL report, never a silent
empty success.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol


class SearchErrorCode(StrEnum):
    """Stable search refusal classes (guide/11 failure semantics)."""

    EMPTY_QUERY = "empty_query"
    TIMEOUT = "timeout"
    UNEXPECTED_CONTENT_TYPE = "unexpected_content_type"
    HTTP_STATUS = "http_status"
    TOO_LARGE = "too_large"
    MALFORMED_RESPONSE = "malformed_response"
    TRANSPORT = "transport"


class WebSearchRefusedError(Exception):
    """
    A search was refused: no report, no partial content (typed failure).

    Hand-written instead of a frozen+slots dataclass: contextlib/anyio assign
    ``__traceback__``/``__cause__`` on exceptions after construction, which
    the dataclass-generated frozen ``__setattr__`` breaks (TypeError).
    Fields stay immutable by convention; nothing reassigns them.
    """

    __slots__ = ("code", "detail")

    def __init__(self, code: SearchErrorCode, detail: str) -> None:
        """Bind the stable refusal code and safe detail."""
        super().__init__(code, detail)
        self.code = code
        self.detail = detail

    def __str__(self) -> str:
        """Return the stable code and safe detail."""
        return f"{self.code.value}: {self.detail}"


class SearchTimeRange(StrEnum):
    """SearXNG ``time_range`` values (docs.searxng.org search API)."""

    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


@dataclass(frozen=True, slots=True)
class SearchBudget:
    """Per-run budget: wall-clock deadline plus token-agnostic cost caps."""

    timeout_seconds: float = 10.0
    max_results: int = 20
    max_response_bytes: int = 2 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class WebSearchCommand:
    """One search request; the query text is untrusted input."""

    query: str
    engines: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    language: str | None = None
    time_range: SearchTimeRange | None = None
    budget: SearchBudget = field(default_factory=SearchBudget)


class SearchOutcome(StrEnum):
    """Whether the engines answered fully or the report is explicitly partial."""

    COMPLETE = "complete"
    PARTIAL = "partial"


class SearchPartialReason(StrEnum):
    """Why a report is partial (never silent: degraded coverage is stated)."""

    ENGINES_UNRESPONSIVE = "engines_unresponsive"
    ALL_ENGINES_UNRESPONSIVE = "all_engines_unresponsive"
    BUDGET_RESULT_CAP = "budget_result_cap"


@dataclass(frozen=True, slots=True)
class SearchHit:
    """One untrusted discovery hit: URL/title/snippet + contributing engines."""

    url: str
    title: str
    snippet: str
    engines: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WebSearchReport:
    """A search answer with explicit completeness semantics (guide/11)."""

    outcome: SearchOutcome
    query: str
    hits: tuple[SearchHit, ...]
    unresponsive_engines: tuple[str, ...]
    partial_reasons: tuple[SearchPartialReason, ...]
    number_of_results: int | None = None


@dataclass(frozen=True, slots=True)
class EngineHealth:
    """One engine's configured state, as observable through SearXNG."""

    engine: str
    enabled: bool
    categories: tuple[str, ...]
    timeout_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class EngineHealthReport:
    """Engine health snapshot (``/config`` view) for observability."""

    engines: tuple[EngineHealth, ...]


class WebSearchPort(Protocol):
    """The discovery surface consumed by the research runtime (ch11)."""

    async def search(self, command: WebSearchCommand) -> WebSearchReport:
        """Run one budgeted search; partials are reports, refusals raise."""
        ...

    async def engine_health(self) -> EngineHealthReport:
        """Return the engine configuration snapshot for health observability."""
        ...


def normalize_query(raw: str) -> str:
    """
    Normalize a query for transport and cache identity.

    NFKC plus whitespace collapsing; case is preserved because upstream
    engines may treat case distinctly. An empty result is a typed refusal.
    """
    normalized = " ".join(unicodedata.normalize("NFKC", raw).split())
    if not normalized:
        raise WebSearchRefusedError(SearchErrorCode.EMPTY_QUERY, "query is empty")
    return normalized

