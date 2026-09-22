"""Adapter contract tests vs the in-process fake SearXNG (RSR-01a 26.4)."""

from __future__ import annotations

import anyio
import httpx
import pytest
from milpbooklm_adapters.searxng import (
    FakeEngineConfig,
    FakeSearchResult,
    FakeSearxng,
    SearxngSearchService,
)
from milpbooklm_application.web_search import (
    EngineHealthReport,
    SearchBudget,
    SearchErrorCode,
    SearchOutcome,
    SearchPartialReason,
    SearchTimeRange,
    WebSearchCommand,
    WebSearchRefusedError,
)


@pytest.fixture
def fake() -> FakeSearxng:
    """A default scripted fake (full-success scenario, no degradation)."""
    return FakeSearxng()


def _service(fake: FakeSearxng) -> SearxngSearchService:
    return SearxngSearchService(
        base_url="http://searxng.test",
        transport=httpx.ASGITransport(app=fake),
    )


# The fake reports len(results) * 13 as the upstream "total" stand-in.
_FAKE_TOTAL_SCALE = 13


def _results(count: int) -> tuple[FakeSearchResult, ...]:
    return tuple(
        FakeSearchResult(
            url=f"https://example.test/{index}",
            title=f"Hit {index}",
            content=f"snippet {index}",
            engines=("duckduckgo", "google"),
        )
        for index in range(count)
    )


def test_search_maps_results_and_sends_params(fake: FakeSearxng) -> None:
    fake.results = _results(2)
    service = _service(fake)
    command = WebSearchCommand(
        query="  quarterly   report ",
        engines=("google", "bing", "google"),
        categories=("general", "it"),
        language="de-DE",
        time_range=SearchTimeRange.WEEK,
    )

    async def drive() -> None:
        report = await service.search(command)
        await service.aclose()
        assert report.outcome is SearchOutcome.COMPLETE
        assert report.query == "quarterly report"
        assert [hit.url for hit in report.hits] == [
            "https://example.test/0",
            "https://example.test/1",
        ]
        assert report.hits[0].title == "Hit 0"
        assert report.hits[0].snippet == "snippet 0"
        assert report.hits[0].engines == ("duckduckgo", "google")
        assert report.unresponsive_engines == ()
        assert report.partial_reasons == ()
        assert report.number_of_results == 2 * _FAKE_TOTAL_SCALE

    anyio.run(drive)
    assert fake.requests[-1] == {
        "path": "/search",
        "q": "quarterly report",
        "format": "json",
        "engines": "bing,google",
        "categories": "general,it",
        "language": "de-DE",
        "time_range": "week",
    }


def test_unresponsive_engines_degrade_to_partial(fake: FakeSearxng) -> None:
    fake.results = _results(1)
    fake.unresponsive_hosts = ("bing",)
    service = _service(fake)

    async def drive() -> None:
        report = await service.search(WebSearchCommand(query="partial engines"))
        await service.aclose()
        assert report.outcome is SearchOutcome.PARTIAL
        assert len(report.hits) == 1
        assert report.unresponsive_engines == ("bing",)
        assert report.partial_reasons == (SearchPartialReason.ENGINES_UNRESPONSIVE,)

    anyio.run(drive)


def test_all_engines_unresponsive_is_explicit_partial(fake: FakeSearxng) -> None:
    fake.results = ()
    fake.unresponsive_hosts = ("bing", "duckduckgo", "google")
    service = _service(fake)

    async def drive() -> None:
        report = await service.search(WebSearchCommand(query="outage"))
        await service.aclose()
        assert report.outcome is SearchOutcome.PARTIAL
        assert report.hits == ()
        assert report.partial_reasons == (SearchPartialReason.ALL_ENGINES_UNRESPONSIVE,)
        assert report.unresponsive_engines == ("bing", "duckduckgo", "google")

    anyio.run(drive)


def test_no_hits_with_healthy_engines_is_complete(fake: FakeSearxng) -> None:
    service = _service(fake)

    async def drive() -> None:
        report = await service.search(WebSearchCommand(query="obscure phrase"))
        await service.aclose()
        assert report.outcome is SearchOutcome.COMPLETE
        assert report.hits == ()

    anyio.run(drive)


def test_wall_clock_deadline_is_a_timeout_refusal(fake: FakeSearxng) -> None:
    fake.results = _results(1)
    fake.delay_seconds = 0.2
    service = _service(fake)
    command = WebSearchCommand(
        query="slow", budget=SearchBudget(timeout_seconds=0.05)
    )

    async def drive() -> None:
        try:
            with pytest.raises(WebSearchRefusedError) as captured:
                await service.search(command)
        finally:
            await service.aclose()
        assert captured.value.code is SearchErrorCode.TIMEOUT

    anyio.run(drive)


def test_unexpected_content_type_is_refused(fake: FakeSearxng) -> None:
    fake.results = _results(1)
    fake.content_type = "text/html"
    service = _service(fake)

    async def drive() -> None:
        try:
            with pytest.raises(WebSearchRefusedError) as captured:
                await service.search(WebSearchCommand(query="misconfigured"))
        finally:
            await service.aclose()
        assert captured.value.code is SearchErrorCode.UNEXPECTED_CONTENT_TYPE

    anyio.run(drive)


def test_json_format_gate_disabled_answers_html_403(fake: FakeSearxng) -> None:
    fake.results = _results(1)
    fake.json_enabled = False
    service = _service(fake)

    async def drive() -> None:
        try:
            with pytest.raises(WebSearchRefusedError) as captured:
                await service.search(WebSearchCommand(query="no json format"))
        finally:
            await service.aclose()
        assert captured.value.code is SearchErrorCode.HTTP_STATUS

    anyio.run(drive)


def test_http_error_status_is_refused(fake: FakeSearxng) -> None:
    fake.status = 503
    service = _service(fake)

    async def drive() -> None:
        try:
            with pytest.raises(WebSearchRefusedError) as captured:
                await service.search(WebSearchCommand(query="overloaded"))
        finally:
            await service.aclose()
        assert captured.value.code is SearchErrorCode.HTTP_STATUS

    anyio.run(drive)


def test_budget_result_cap_yields_partial_with_reason(fake: FakeSearxng) -> None:
    fake.results = _results(8)
    service = _service(fake)
    cap = 3
    command = WebSearchCommand(query="capped", budget=SearchBudget(max_results=cap))

    async def drive() -> None:
        report = await service.search(command)
        await service.aclose()
        assert report.outcome is SearchOutcome.PARTIAL
        assert len(report.hits) == cap
        assert report.partial_reasons == (SearchPartialReason.BUDGET_RESULT_CAP,)

    anyio.run(drive)


def test_response_byte_cap_is_refused(fake: FakeSearxng) -> None:
    fake.results = _results(4)
    service = _service(fake)
    command = WebSearchCommand(query="big", budget=SearchBudget(max_response_bytes=64))

    async def drive() -> None:
        try:
            with pytest.raises(WebSearchRefusedError) as captured:
                await service.search(command)
        finally:
            await service.aclose()
        assert captured.value.code is SearchErrorCode.TOO_LARGE

    anyio.run(drive)


def test_malformed_json_body_is_refused(fake: FakeSearxng) -> None:
    fake.raw_body = b"<html>proxy error page</html>"
    service = _service(fake)

    async def drive() -> None:
        try:
            with pytest.raises(WebSearchRefusedError) as captured:
                await service.search(WebSearchCommand(query="broken body"))
        finally:
            await service.aclose()
        assert captured.value.code is SearchErrorCode.MALFORMED_RESPONSE

    anyio.run(drive)


def test_engine_health_reports_config_engines(fake: FakeSearxng) -> None:
    fake.config_engines = (
        FakeEngineConfig(name="duckduckgo"),
        FakeEngineConfig(name="wikipedia", enabled=False, categories=("wikipedia",)),
    )
    service = _service(fake)

    async def drive() -> None:
        report = await service.engine_health()
        await service.aclose()
        assert isinstance(report, EngineHealthReport)
        assert [(entry.engine, entry.enabled) for entry in report.engines] == [
            ("duckduckgo", True),
            ("wikipedia", False),
        ]
        assert report.engines[1].categories == ("wikipedia",)

    anyio.run(drive)
    assert fake.requests[-1]["path"] == "/config"


def test_empty_query_is_refused_before_any_request(fake: FakeSearxng) -> None:
    service = _service(fake)

    async def drive() -> None:
        try:
            with pytest.raises(WebSearchRefusedError) as captured:
                await service.search(WebSearchCommand(query="   "))
        finally:
            await service.aclose()
        assert captured.value.code is SearchErrorCode.EMPTY_QUERY

    anyio.run(drive)
    assert fake.requests == []


def test_default_config_revision_tracks_pinned_version() -> None:
    service = SearxngSearchService(base_url="http://searxng.test")
    assert service.config_revision == "searxng:2026.9.20-2e624bed4"
