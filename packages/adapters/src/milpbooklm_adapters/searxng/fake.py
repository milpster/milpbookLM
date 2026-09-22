"""
Deterministic in-process fake SearXNG for CI (RSR-01a 26.4, guide/11 Testing).

A pure-ASGI application (no framework dependency, no network, no running
service) that speaks enough of the SearXNG HTTP surface for the REAL adapter
to be exercised end-to-end: ``/search`` (JSON format gate included),
``/config`` (engine list), and ``/healthz``. Scenarios are constructor-bound
and every request is recorded for parameter assertions.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, MutableMapping
from dataclasses import dataclass, field
from typing import Any, Final
from urllib.parse import parse_qsl

import anyio

type AsgiScope = MutableMapping[str, Any]
type AsgiMessage = MutableMapping[str, Any]
type AsgiReceive = Callable[[], Awaitable[AsgiMessage]]
type AsgiSend = Callable[[AsgiMessage], Awaitable[None]]
type AsgiApp = Callable[[AsgiScope, AsgiReceive, AsgiSend], Awaitable[None]]

_SCOPE_TYPE_HTTP: Final = "http"


@dataclass(frozen=True, slots=True)
class FakeEngineConfig:
    """One ``/config`` engine entry served by the fake."""

    name: str
    enabled: bool = True
    categories: tuple[str, ...] = ("general",)
    timeout: float = 3.0


@dataclass(frozen=True, slots=True)
class FakeSearchResult:
    """One ``/search`` result entry served by the fake."""

    url: str
    title: str
    content: str = ""
    engines: tuple[str, ...] = ()


DEFAULT_CONFIG_ENGINES: Final = (
    FakeEngineConfig(name="duckduckgo"),
    FakeEngineConfig(name="google"),
    FakeEngineConfig(name="wikipedia", enabled=False, categories=("general", "wikipedia")),
)


@dataclass(slots=True)
class FakeSearxng:
    """Scriptable SearXNG double: full/partial/timeout/bad-type scenarios."""

    results: tuple[FakeSearchResult, ...] = ()
    unresponsive_hosts: tuple[str, ...] = ()
    content_type: str = "application/json"
    status: int = 200
    delay_seconds: float = 0.0
    json_enabled: bool = True
    raw_body: bytes | None = None
    config_engines: tuple[FakeEngineConfig, ...] = DEFAULT_CONFIG_ENGINES
    requests: list[dict[str, str]] = field(default_factory=list)

    async def __call__(self, scope: AsgiScope, receive: AsgiReceive, send: AsgiSend) -> None:
        """Serve one ASGI HTTP request from the scripted scenario."""
        del receive  # GET-only surface: no request body is ever sent
        if scope["type"] != _SCOPE_TYPE_HTTP:
            raise ValueError(f"unsupported scope type {scope['type']!r}")
        path = str(scope["path"])
        query_string = scope["query_string"]
        if not isinstance(query_string, bytes):
            raise ValueError("ASGI query_string must be bytes")
        params = dict(parse_qsl(query_string.decode()))
        self.requests.append({"path": path, **params})
        if self.delay_seconds:
            await anyio.sleep(self.delay_seconds)
        if path == "/search":
            await self._search(params, send)
        elif path == "/config":
            await self._config(send)
        else:
            await _respond(send, 404, "application/json", b'{"error": "not found"}')

    async def _search(
        self, params: dict[str, str], send: Callable[[dict[str, object]], Awaitable[None]]
    ) -> None:
        """Answer /search; a disabled JSON format yields the real 403 HTML page."""
        if not self.json_enabled or params.get("format") != "json":
            await _respond(
                send, 403, "text/html", b"<html><body>403 Forbidden</body></html>"
            )
            return
        payload = {
            "query": params.get("q", ""),
            "number_of_results": 13 * max(len(self.results), 1),
            "results": [
                {
                    "url": result.url,
                    "title": result.title,
                    "content": result.content,
                    "engines": list(result.engines),
                }
                for result in self.results
            ],
            "answers": [],
            "infoboxes": [],
            "suggestions": [],
            "unresponsive_hosts": list(self.unresponsive_hosts),
        }
        await _respond(
            send, self.status, self.content_type, self.raw_body or json.dumps(payload).encode()
        )

    async def _config(self, send: Callable[[dict[str, object]], Awaitable[None]]) -> None:
        """Answer /config with the scripted engine list."""
        payload = {
            "engines": [
                {
                    "name": engine.name,
                    "enabled": engine.enabled,
                    "categories": list(engine.categories),
                    "timeout": engine.timeout,
                }
                for engine in self.config_engines
            ]
        }
        await _respond(
            send, self.status, self.content_type, self.raw_body or json.dumps(payload).encode()
        )


async def _respond(
    send: Callable[[dict[str, object]], Awaitable[None]],
    status: int,
    content_type: str,
    body: bytes,
) -> None:
    """Emit one complete ASGI HTTP response."""
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", content_type.encode())],
        }
    )
    await send({"type": "http.response.body", "body": body})
