"""
Payload parsing for the SearXNG adapter boundary (RSR-01a 26.2).

The SearXNG JSON payload is untrusted input; it is parsed here into typed
values exactly once — malformed payloads become typed refusals, and no raw
payload shapes travel deeper than this module.
"""

from __future__ import annotations

import json

from milpbooklm_application.web_search import (
    EngineHealth,
    SearchErrorCode,
    SearchHit,
    WebSearchRefusedError,
)

JSON_MEDIA_TYPE = "application/json"


def parse_payload(body: bytes) -> dict[str, object]:
    """Parse the JSON body; malformed bodies are typed refusals."""
    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise WebSearchRefusedError(
            SearchErrorCode.MALFORMED_RESPONSE, f"invalid JSON body ({exc})"
        ) from exc
    if not isinstance(payload, dict):
        raise WebSearchRefusedError(
            SearchErrorCode.MALFORMED_RESPONSE, "JSON body is not an object"
        )
    return payload


def parse_hits(payload: dict[str, object]) -> tuple[SearchHit, ...]:
    """Map the SearXNG result list to typed hits (strict field contract)."""
    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        raise WebSearchRefusedError(
            SearchErrorCode.MALFORMED_RESPONSE, "response has no results list"
        )
    hits = []
    for entry in raw_results:
        if not isinstance(entry, dict):
            raise WebSearchRefusedError(
                SearchErrorCode.MALFORMED_RESPONSE, "result entry is not an object"
            )
        url = entry.get("url")
        if not isinstance(url, str) or not url:
            raise WebSearchRefusedError(
                SearchErrorCode.MALFORMED_RESPONSE, "result entry has no url"
            )
        engines = entry.get("engines")
        hits.append(
            SearchHit(
                url=url,
                title=_string_or_empty(entry.get("title")),
                snippet=_string_or_empty(entry.get("content")),
                engines=tuple(str(engine) for engine in engines)
                if isinstance(engines, list)
                else (),
            )
        )
    return tuple(hits)


def parse_unresponsive(payload: dict[str, object]) -> tuple[str, ...]:
    """Record engines that failed/timed out upstream (explicit degradation)."""
    raw = payload.get("unresponsive_hosts")
    if not isinstance(raw, list):
        return ()
    return tuple(item for item in raw if isinstance(item, str))


def parse_engine_health(payload: dict[str, object]) -> tuple[EngineHealth, ...]:
    """Parse the ``/config`` engines list into typed health entries."""
    raw_engines = payload.get("engines")
    if not isinstance(raw_engines, list):
        raise WebSearchRefusedError(
            SearchErrorCode.MALFORMED_RESPONSE, "config has no engines list"
        )
    return tuple(_engine_health(entry) for entry in raw_engines)


def _engine_health(entry: object) -> EngineHealth:
    """Parse one ``/config`` engine entry defensively at this boundary."""
    if not isinstance(entry, dict):
        raise WebSearchRefusedError(
            SearchErrorCode.MALFORMED_RESPONSE, "config engine entry is not an object"
        )
    timeout = entry.get("timeout")
    categories = entry.get("categories")
    return EngineHealth(
        engine=_string_or_empty(entry.get("name")),
        enabled=bool(entry.get("enabled", False)),
        categories=tuple(str(category) for category in categories)
        if isinstance(categories, list)
        else (),
        timeout_seconds=float(timeout) if isinstance(timeout, int | float) else None,
    )


def _string_or_empty(value: object) -> str:
    """Coerce an optional string field; absent fields are honest empties."""
    return value if isinstance(value, str) else ""


def media_type(content_type: str) -> str:
    """Extract the bare media type, lowercase (parameters ignored)."""
    return content_type.split(";", 1)[0].strip().lower()
