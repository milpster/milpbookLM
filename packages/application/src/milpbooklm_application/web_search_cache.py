"""
Short-TTL bounded cache for web search (RSR-01a 26.3, guide/11 SearXNG).

Keyed by the normalized query plus the search parameters AND the SearXNG
configuration revision, so a deployment/config change immediately invalidates
old answers. Only COMPLETE reports are cached: partial (degraded/timeout)
answers are always re-queried, and entries expire after a short TTL measured
on an injectable monotonic clock.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

from milpbooklm_application.web_search import (
    EngineHealthReport,
    SearchOutcome,
    WebSearchCommand,
    WebSearchPort,
    WebSearchReport,
    normalize_query,
)

_CacheKey = tuple[str, tuple[str, ...], tuple[str, ...], str, str, str]


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    """A cached complete report plus its monotonic storage timestamp."""

    report: WebSearchReport
    stored_at: float


def _cache_key(command: WebSearchCommand, config_revision: str) -> _CacheKey:
    """Canonical identity: normalized query, sorted params, config revision."""
    time_range = command.time_range.value if command.time_range else ""
    return (
        normalize_query(command.query),
        tuple(sorted(set(command.engines))),
        tuple(sorted(set(command.categories))),
        command.language or "",
        time_range,
        config_revision,
    )


class CachedWebSearch:
    """Bounded TTL cache decorating a WebSearchPort (guide/11 cache rule)."""

    def __init__(
        self,
        *,
        inner: WebSearchPort,
        config_revision: str,
        ttl_seconds: float = 120.0,
        max_entries: int = 256,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Bind the delegate port, the config revision, TTL bound and clock."""
        self._inner = inner
        self._config_revision = config_revision
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._entries: OrderedDict[_CacheKey, _CacheEntry] = OrderedDict()

    async def search(self, command: WebSearchCommand) -> WebSearchReport:
        """Serve a fresh complete hit from cache, otherwise query the delegate."""
        key = _cache_key(command, self._config_revision)
        now = self._clock()
        entry = self._entries.get(key)
        if entry is not None and now - entry.stored_at <= self._ttl_seconds:
            self._entries.move_to_end(key)
            return entry.report
        report = await self._inner.search(command)
        if report.outcome is SearchOutcome.COMPLETE:
            self._entries[key] = _CacheEntry(report=report, stored_at=now)
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)
        return report

    async def engine_health(self) -> EngineHealthReport:
        """Delegate engine health (health is live configuration, never cached)."""
        return await self._inner.engine_health()
