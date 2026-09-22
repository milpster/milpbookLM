"""Unit tests for the bounded TTL web-search cache (RSR-01a 26.3)."""

from __future__ import annotations

import anyio
from milpbooklm_application.web_search import (
    EngineHealthReport,
    SearchOutcome,
    SearchPartialReason,
    SearchTimeRange,
    WebSearchCommand,
    WebSearchPort,
    WebSearchReport,
)
from milpbooklm_application.web_search_cache import CachedWebSearch

# FND-02 rule 5: expected delegate call counts are named, not magic.
_TWO_CALLS = 2
_THREE_CALLS = 3


class _Clock:
    """A manually advanced monotonic clock for deterministic TTL tests."""

    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class _ScriptedPort:
    """A recording WebSearchPort double returning one scripted report."""

    def __init__(self, report: WebSearchReport) -> None:
        self.report = report
        self.searches = 0
        self.health_calls = 0

    async def search(self, command: WebSearchCommand) -> WebSearchReport:
        self.searches += 1
        return self.report

    async def engine_health(self) -> EngineHealthReport:
        self.health_calls += 1
        return EngineHealthReport(engines=())


def _complete(query: str = "cache me") -> WebSearchReport:
    return WebSearchReport(
        outcome=SearchOutcome.COMPLETE,
        query=query,
        hits=(),
        unresponsive_engines=(),
        partial_reasons=(),
        number_of_results=0,
    )


def test_complete_report_is_served_from_cache_within_ttl() -> None:
    port = _ScriptedPort(_complete())
    cache = CachedWebSearch(inner=port, config_revision="r1", clock=_Clock())
    command = WebSearchCommand(query="cache me")

    async def drive() -> None:
        first = await cache.search(command)
        second = await cache.search(command)
        assert second is first

    anyio.run(drive)
    assert port.searches == 1


def test_expired_entry_is_requeried() -> None:
    port = _ScriptedPort(_complete())
    clock = _Clock()
    cache = CachedWebSearch(
        inner=port, config_revision="r1", ttl_seconds=10.0, clock=clock
    )

    async def drive() -> None:
        await cache.search(WebSearchCommand(query="cache me"))
        clock.now += 10.5
        await cache.search(WebSearchCommand(query="cache me"))

    anyio.run(drive)
    assert port.searches == _TWO_CALLS


def test_partial_reports_are_never_cached() -> None:
    report = WebSearchReport(
        outcome=SearchOutcome.PARTIAL,
        query="degraded",
        hits=(),
        unresponsive_engines=("bing",),
        partial_reasons=(SearchPartialReason.ENGINES_UNRESPONSIVE,),
    )
    port = _ScriptedPort(report)
    cache = CachedWebSearch(inner=port, config_revision="r1", clock=_Clock())

    async def drive() -> None:
        await cache.search(WebSearchCommand(query="degraded"))
        await cache.search(WebSearchCommand(query="degraded"))

    anyio.run(drive)
    assert port.searches == _TWO_CALLS


def test_config_revision_invalidates_the_key() -> None:
    port = _ScriptedPort(_complete())
    command = WebSearchCommand(query="cache me")

    async def drive() -> None:
        await CachedWebSearch(inner=port, config_revision="r1", clock=_Clock()).search(
            command
        )
        await CachedWebSearch(inner=port, config_revision="r2", clock=_Clock()).search(
            command
        )

    anyio.run(drive)
    assert port.searches == _TWO_CALLS


def test_cache_is_bounded_by_max_entries() -> None:
    port = _ScriptedPort(_complete())
    cache = CachedWebSearch(
        inner=port, config_revision="r1", max_entries=1, clock=_Clock()
    )

    async def drive() -> None:
        await cache.search(WebSearchCommand(query="first"))
        await cache.search(WebSearchCommand(query="second"))
        await cache.search(WebSearchCommand(query="first"))

    anyio.run(drive)
    assert port.searches == _THREE_CALLS


def test_key_normalizes_query_whitespace_and_param_order() -> None:
    port = _ScriptedPort(_complete("quarterly report"))
    cache = CachedWebSearch(inner=port, config_revision="r1", clock=_Clock())

    async def drive() -> None:
        await cache.search(
            WebSearchCommand(
                query="  quarterly   report ",
                engines=("google", "bing"),
                categories=("it", "general"),
            )
        )
        await cache.search(
            WebSearchCommand(
                query="quarterly report",
                engines=("bing", "google"),
                categories=("general", "it"),
            )
        )

    anyio.run(drive)
    assert port.searches == 1


def test_distinct_params_miss_the_cache() -> None:
    port = _ScriptedPort(_complete())
    cache = CachedWebSearch(inner=port, config_revision="r1", clock=_Clock())

    async def drive() -> None:
        await cache.search(WebSearchCommand(query="same query"))
        await cache.search(
            WebSearchCommand(query="same query", time_range=SearchTimeRange.DAY)
        )
        await cache.search(WebSearchCommand(query="same query", language="de-DE"))

    anyio.run(drive)
    assert port.searches == _THREE_CALLS


def test_engine_health_is_delegated_not_cached() -> None:
    port = _ScriptedPort(_complete())
    cache = CachedWebSearch(inner=port, config_revision="r1", clock=_Clock())

    async def drive() -> None:
        await cache.engine_health()
        await cache.engine_health()

    anyio.run(drive)
    assert port.health_calls == _TWO_CALLS


def test_scripted_port_satisfies_the_port_protocol() -> None:
    port: WebSearchPort = _ScriptedPort(_complete())
    assert port is not None
