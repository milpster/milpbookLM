"""
SearXNG adapter (RSR-01a 26.2, guide/11 SearXNG section, TECH-11-001).

Provider-shaped implementation of the application ``WebSearchPort``:

* calls the JSON search API with engine/category/language/time parameters;
* a per-run budget bounds wall-clock time (anyio deadline covering headers
  AND body), result count, and response bytes;
* unexpected content types are rejected (JSON must be enabled in deployment
  settings — a misconfigured instance answers with an HTML page);
* hits record URL/title/snippet plus contributing engines, and unresponsive
  engines degrade the answer to an EXPLICIT partial report (never a silent
  empty success);
* engine health is observable through the instance ``/config`` endpoint.

Results are untrusted discovery data; only the hardened fetch service and
ingestion controls may act on them.
"""

from __future__ import annotations

import logging
from typing import Final

import anyio
import httpx
from milpbooklm_application.web_search import (
    EngineHealthReport,
    SearchBudget,
    SearchErrorCode,
    SearchOutcome,
    SearchPartialReason,
    WebSearchCommand,
    WebSearchRefusedError,
    WebSearchReport,
    normalize_query,
)

from .parsing import (
    JSON_MEDIA_TYPE,
    media_type,
    parse_engine_health,
    parse_hits,
    parse_payload,
    parse_unresponsive,
)

logger = logging.getLogger(__name__)

# Mirrors infra/podman/versions.lock SEARXNG_VERSION — keep both in sync.
SEARXNG_VERSION: Final = "2026.9.20-2e624bed4"
# docs.searxng.org search API: success is HTTP 200 with the JSON payload.
_HTTP_OK: Final = 200
_HEALTH_TIMEOUT_SECONDS: Final = 10.0
_HEALTH_MAX_BYTES: Final = 4 * 1024 * 1024
_CLIENT_TIMEOUT_BACKSTOP: Final = 60.0


class SearxngSearchService:
    """SearXNG search + engine-health adapter over one service-owned client."""

    def __init__(
        self,
        *,
        base_url: str = "http://searxng:8080",
        transport: httpx.AsyncBaseTransport | None = None,
        config_revision: str | None = None,
    ) -> None:
        """Bind the instance URL, injectable transport, and config revision."""
        self._base_url = base_url.rstrip("/")
        self._config_revision = config_revision or f"searxng:{SEARXNG_VERSION}"
        self._client = httpx.AsyncClient(
            transport=transport,
            headers={"Accept": JSON_MEDIA_TYPE},
            timeout=httpx.Timeout(_CLIENT_TIMEOUT_BACKSTOP),
            trust_env=False,
        )

    @property
    def config_revision(self) -> str:
        """The deployment revision cache keys must be invalidated by."""
        return self._config_revision

    async def search(self, command: WebSearchCommand) -> WebSearchReport:
        """Run one budgeted JSON search with explicit partial semantics."""
        query = normalize_query(command.query)
        body = await self._exchange(
            f"{self._base_url}/search", _request_params(command, query), command.budget
        )
        payload = parse_payload(body)
        return _report(query, payload, command.budget.max_results)

    async def engine_health(self) -> EngineHealthReport:
        """Snapshot engine configuration from the instance ``/config``."""
        budget = SearchBudget(
            timeout_seconds=_HEALTH_TIMEOUT_SECONDS,
            max_response_bytes=_HEALTH_MAX_BYTES,
        )
        body = await self._exchange(f"{self._base_url}/config", {}, budget)
        return EngineHealthReport(engines=parse_engine_health(parse_payload(body)))

    async def _exchange(
        self, url: str, params: dict[str, str], budget: SearchBudget
    ) -> bytes:
        """One deadline-bounded GET with strict status/content-type/byte gates."""
        try:
            with anyio.fail_after(budget.timeout_seconds):
                response = await self._client.send(
                    self._client.build_request("GET", url, params=params),
                    stream=True,
                )
                try:
                    if response.status_code != _HTTP_OK:
                        # A 403 HTML page is SearXNG's "format not allowed"
                        # answer when the JSON format was not enabled.
                        raise WebSearchRefusedError(
                            SearchErrorCode.HTTP_STATUS,
                            f"upstream returned HTTP {response.status_code}",
                        )
                    got_type = media_type(response.headers.get("content-type", ""))
                    if got_type != JSON_MEDIA_TYPE:
                        raise WebSearchRefusedError(
                            SearchErrorCode.UNEXPECTED_CONTENT_TYPE,
                            f"expected {JSON_MEDIA_TYPE}, got {got_type!r}",
                        )
                    return await _read_capped(response, budget.max_response_bytes)
                finally:
                    await response.aclose()
        except httpx.TimeoutException as exc:
            raise WebSearchRefusedError(
                SearchErrorCode.TIMEOUT, "connect/read timeout"
            ) from exc
        except TimeoutError as exc:
            raise WebSearchRefusedError(
                SearchErrorCode.TIMEOUT, "wall-clock search limit"
            ) from exc
        except httpx.HTTPError as exc:
            raise WebSearchRefusedError(
                SearchErrorCode.TRANSPORT, type(exc).__name__
            ) from exc

    async def aclose(self) -> None:
        """Release the pooled connections."""
        await self._client.aclose()


def _request_params(command: WebSearchCommand, query: str) -> dict[str, str]:
    """Map the command to SearXNG query parameters (docs.searxng.org)."""
    params = {"q": query, "format": "json"}
    if command.engines:
        params["engines"] = ",".join(sorted(set(command.engines)))
    if command.categories:
        params["categories"] = ",".join(sorted(set(command.categories)))
    if command.language:
        params["language"] = command.language
    if command.time_range:
        params["time_range"] = command.time_range.value
    return params


def _report(
    query: str, payload: dict[str, object], max_results: int
) -> WebSearchReport:
    """Build the report with explicit partial semantics and budget caps."""
    hits = parse_hits(payload)
    unresponsive = parse_unresponsive(payload)
    reasons: list[SearchPartialReason] = []
    if len(hits) > max_results:
        hits = hits[:max_results]
        reasons.append(SearchPartialReason.BUDGET_RESULT_CAP)
    if unresponsive:
        reasons.append(
            SearchPartialReason.ALL_ENGINES_UNRESPONSIVE
            if not hits
            else SearchPartialReason.ENGINES_UNRESPONSIVE
        )
    if reasons:
        logger.info(
            "partial search answer: query=%r reasons=%s unresponsive=%s",
            query,
            [reason.value for reason in reasons],
            unresponsive,
        )
    number = payload.get("number_of_results")
    return WebSearchReport(
        outcome=SearchOutcome.PARTIAL if reasons else SearchOutcome.COMPLETE,
        query=query,
        hits=hits,
        unresponsive_engines=unresponsive,
        partial_reasons=tuple(reasons),
        number_of_results=number if isinstance(number, int) else None,
    )


async def _read_capped(response: httpx.Response, max_bytes: int) -> bytes:
    """Stream the body with an early abort at the byte budget."""
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > max_bytes:
            raise WebSearchRefusedError(
                SearchErrorCode.TOO_LARGE, f"response exceeds {max_bytes} byte budget"
            )
        chunks.append(chunk)
    return b"".join(chunks)
