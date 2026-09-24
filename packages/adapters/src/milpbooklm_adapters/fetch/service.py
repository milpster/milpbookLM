"""
Hardened fetch service: the ONLY outbound fetch path (guide/11 Fetching, guide/19).

Guarantees enforced here and in the pinned transport:
* only http/https, no embedded credentials, only standard web ports (policy);
* every candidate address of every host (first hop, EVERY redirect hop, and
  any proxy destination) is resolved and validated BEFORE any socket exists;
* the connection is pinned to the validated NUMERIC address (no second DNS);
* redirects are followed manually: each hop's URL is re-normalized and the
  hop's target addresses are re-validated by the transport before connecting;
* byte cap with early abort, wall-clock deadline, redirect cap;
* full recording: capture timestamp, redirect chain, final URL, response
  headers, content hash.

Provider-shaped: implements the application's ``WebFetchPort`` so the same
service can serve ingestion (this task) and the research runtime (ch11).
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final
from urllib.parse import urljoin

import anyio
import httpx
from milpbooklm_application.web_fetch import (
    FetchedWebContent,
    FetchErrorCode,
    WebFetchCommand,
    WebFetchRecord,
    WebFetchRefusedError,
)

from .addressing import (
    AddressResolver,
    SSRFBlockedError,
    default_resolver,
    select_pinned_address,
)
from .pinned import PinnedFetchTransport
from .urls import ALLOWED_PORTS, FetchPolicyError, FetchTarget, normalize_url

logger = logging.getLogger(__name__)

USER_AGENT: Final = "milpbookLM/0.1 (self-hosted research notebook; static fetch)"
_HTTP_ERROR_STATUS: Final = 400
_RECORDED_HEADERS: Final = frozenset(
    {"cache-control", "content-language", "content-type", "etag", "last-modified"}
)
# Standard egress-proxy ports for the proxy-destination enforcement hook.
_PROXY_PORTS: Final = frozenset({80, 443, 3128, 8080, 8888, 1080})


@dataclass(frozen=True, slots=True)
class FetchLimits:
    """Declared caps for every fetch (guide/19: cap bytes, time and redirects)."""

    max_bytes: int = 10 * 1024 * 1024
    max_redirects: int = 5
    timeout_seconds: float = 20.0
    allowed_ports: frozenset[int] = ALLOWED_PORTS


class HardenedFetchService:
    """Dedicated fetch service (WebFetchPort): validation-pinned, capped, recorded."""

    def __init__(
        self,
        *,
        limits: FetchLimits | None = None,
        resolver: AddressResolver | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Bind caps, the injectable resolver, and the pinned transport."""
        self._limits = limits or FetchLimits()
        self._resolver = resolver or default_resolver
        self._transport = transport or PinnedFetchTransport(resolver=self._resolver)
        self._client = httpx.AsyncClient(
            transport=self._transport,
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT},
            timeout=httpx.Timeout(5.0),
            trust_env=False,
        )
    def validate_proxy_destination(self, proxy_url: str) -> None:
        """Apply the same pre-connect policy to a trusted egress proxy endpoint."""
        target = normalize_url(proxy_url, allowed_ports=_PROXY_PORTS)
        select_pinned_address(target.host, target.port, resolver=self._resolver)

    async def fetch(self, command: WebFetchCommand) -> FetchedWebContent:
        """Fetch one URL through the pinned transport with full recording."""
        deadline = time.monotonic() + self._limits.timeout_seconds
        target = _normalize_target(command.url, self._limits.allowed_ports)
        chain: list[str] = []
        try:
            for _hop in range(self._limits.max_redirects + 1):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise WebFetchRefusedError(FetchErrorCode.TIMEOUT, "wall-clock fetch limit")
                with anyio.fail_after(remaining):
                    response = await self._client.send(
                        httpx.Request("GET", target.url), stream=True
                    )
                    try:
                        if response.is_redirect and "location" in response.headers:
                            chain.append(target.url)
                            # Re-validate the hop: scheme/port/credentials here, all
                            # target addresses in the transport before the next connect.
                            location = response.headers["location"]
                            target = _normalize_target(
                                urljoin(target.url, location), self._limits.allowed_ports
                            )
                            continue
                        if response.status_code >= _HTTP_ERROR_STATUS:
                            raise WebFetchRefusedError(
                                FetchErrorCode.INTERNAL,
                                f"upstream returned HTTP {response.status_code}",
                            )
                        body = await _read_capped(response, self._limits.max_bytes)
                    finally:
                        await response.aclose()
                return self._recorded(command.url, target.url, chain, response, body)
            raise WebFetchRefusedError(
                FetchErrorCode.POLICY_BLOCKED, f"exceeded {self._limits.max_redirects} redirects"
            )
        except SSRFBlockedError as exc:
            logger.warning(
                "fetch destination refused pre-connect: host=%s address=%s reason=%s url=%s",
                exc.host,
                exc.address,
                exc.reason,
                command.url,
            )
            raise WebFetchRefusedError(
                FetchErrorCode.POLICY_BLOCKED,
                f"destination {exc.host} refused ({exc.reason})",
            ) from exc
        except httpx.TimeoutException as exc:
            raise WebFetchRefusedError(FetchErrorCode.TIMEOUT, "connect/read timeout") from exc
        except TimeoutError as exc:
            raise WebFetchRefusedError(FetchErrorCode.TIMEOUT, "wall-clock fetch limit") from exc
        except httpx.HTTPError as exc:
            raise WebFetchRefusedError(FetchErrorCode.INTERNAL, type(exc).__name__) from exc

    def _recorded(
        self,
        requested_url: str,
        final_url: str,
        chain: list[str],
        response: httpx.Response,
        body: bytes,
    ) -> FetchedWebContent:
        """Stamp the capture record: timestamp, chain, final URL, headers, hash."""
        headers = tuple(
            (key.lower(), value)
            for key, value in response.headers.multi_items()
            if key.lower() in _RECORDED_HEADERS
        )
        record = WebFetchRecord(
            requested_url=requested_url,
            final_url=final_url,
            captured_at=datetime.now(UTC).isoformat(),
            status_code=response.status_code,
            content_sha256=hashlib.sha256(body).hexdigest(),
            size_bytes=len(body),
            content_type=response.headers.get("content-type", ""),
            redirect_chain=tuple(chain),
        )
        return FetchedWebContent(body=body, record=record, headers=headers)

    async def aclose(self) -> None:
        """Release the pooled connections."""
        await self._client.aclose()


async def _read_capped(response: httpx.Response, max_bytes: int) -> bytes:
    """Stream the body with an early abort at the byte cap (no full download)."""
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > max_bytes:
            raise WebFetchRefusedError(
                FetchErrorCode.TOO_LARGE, f"content exceeds {max_bytes} byte fetch limit"
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _normalize_target(url: str, allowed_ports: frozenset[int]) -> FetchTarget:
    try:
        return normalize_url(url, allowed_ports=allowed_ports)
    except FetchPolicyError as exc:
        raise WebFetchRefusedError(FetchErrorCode.POLICY_BLOCKED, str(exc)) from exc
