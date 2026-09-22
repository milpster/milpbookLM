from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator, Iterable
from typing import override

import anyio
import httpcore
import httpx
import pytest
from milpbooklm_adapters.fetch import (
    FetchLimits,
    HardenedFetchService,
    PinnedFetchTransport,
    SSRFBlockedError,
    ValidatingNetworkBackend,
    classify_address,
    normalize_url,
)
from milpbooklm_application.web_fetch import (
    FetchErrorCode,
    WebFetchCommand,
    WebFetchRefusedError,
)


class _RecordingBackend(httpcore.AsyncMockBackend):
    def __init__(self, buffer: list[bytes]) -> None:
        super().__init__(buffer)
        self.connections: list[tuple[str, int]] = []

    @override
    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        self.connections.append((host, port))
        return await super().connect_tcp(host, port, timeout, local_address, socket_options)


class _SlowStream(httpx.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b"<html>"
        await anyio.sleep(0.05)
        yield b"</html>"


@pytest.mark.parametrize(
    ("address", "reason"),
    [
        ("127.0.0.1", "loopback"),
        ("10.0.0.1", "private_range"),
        ("169.254.169.254", "link_local_metadata"),
        ("224.0.0.1", "multicast"),
        ("::1", "loopback"),
        ("fe80::1", "link_local"),
        ("fc00::1", "private_range"),
        ("ff02::1", "multicast"),
        ("::ffff:169.254.169.254", "link_local_metadata"),
        ("64:ff9b::a9fe:a9fe", "link_local_metadata"),
    ],
)
def test_classify_address_blocks_non_public_ranges(address: str, reason: str) -> None:
    assert classify_address(address) == reason


def test_numeric_private_target_is_refused_before_connector() -> None:
    backend = _RecordingBackend([])
    validating = ValidatingNetworkBackend(backend, lambda _host, _port: [])

    async def drive() -> None:
        with pytest.raises(SSRFBlockedError):
            await validating.connect_tcp("169.254.169.254", 80)

    anyio.run(drive)
    assert backend.connections == []


def test_all_dns_candidates_are_validated_before_connector() -> None:
    backend = _RecordingBackend([])
    validating = ValidatingNetworkBackend(
        backend,
        lambda _host, _port: ["93.184.216.34", "10.0.0.9"],
    )

    async def drive() -> None:
        with pytest.raises(SSRFBlockedError):
            await validating.connect_tcp("example.test", 443)

    anyio.run(drive)
    assert backend.connections == []


def test_rebinding_second_resolution_is_refused_before_second_connect() -> None:
    backend = _RecordingBackend([])
    answers = iter((["93.184.216.34"], ["127.0.0.1"]))
    validating = ValidatingNetworkBackend(backend, lambda _host, _port: next(answers))

    async def drive() -> None:
        await validating.connect_tcp("example.test", 80)
        with pytest.raises(SSRFBlockedError):
            await validating.connect_tcp("example.test", 80)

    anyio.run(drive)
    assert backend.connections == [("93.184.216.34", 80)]


def test_redirect_to_metadata_is_refused_before_connect() -> None:
    response = [
        b"HTTP/1.1 302 Found\r\n",
        b"Location: http://169.254.169.254/latest/meta-data\r\n",
        b"Content-Length: 0\r\n\r\n",
    ]
    backend = _RecordingBackend(response)
    transport = PinnedFetchTransport(
        resolver=lambda _host, _port: ["93.184.216.34"],
        network_backend=backend,
    )
    service = HardenedFetchService(transport=transport)

    async def drive() -> None:
        with pytest.raises(WebFetchRefusedError) as captured:
            await service.fetch(WebFetchCommand("http://example.test/start"))
        await service.aclose()
        assert captured.value.code is FetchErrorCode.POLICY_BLOCKED

    anyio.run(drive)
    assert backend.connections == [("93.184.216.34", 80)]


def test_snapshot_records_final_url_headers_hash_and_body() -> None:
    body = b"<!doctype html><html><main><h1>Atlas</h1><p>Snapshot.</p></main></html>"
    response = [
        b"HTTP/1.1 200 OK\r\n",
        b"Content-Type: text/html; charset=utf-8\r\n",
        b"ETag: golden-v1\r\n",
        f"Content-Length: {len(body)}\r\n\r\n".encode(),
        body,
    ]
    backend = _RecordingBackend(response)
    transport = PinnedFetchTransport(
        resolver=lambda _host, _port: ["93.184.216.34"],
        network_backend=backend,
    )
    service = HardenedFetchService(transport=transport)

    async def drive() -> None:
        fetched = await service.fetch(WebFetchCommand("HTTPS://Example.Test/report#ignored"))
        await service.aclose()
        assert fetched.body == body
        assert fetched.record.final_url == "https://example.test/report"
        assert fetched.record.content_sha256 == hashlib.sha256(body).hexdigest()
        assert fetched.record.redirect_chain == ()
        assert ("etag", "golden-v1") in fetched.headers
        assert fetched.record.captured_at.endswith("+00:00")

    anyio.run(drive)
    assert backend.connections == [("93.184.216.34", 443)]


def test_wall_clock_limit_applies_while_streaming_body() -> None:
    async def drive() -> None:
        transport = httpx.MockTransport(
            lambda _request: httpx.Response(200, stream=_SlowStream())
        )
        service = HardenedFetchService(
            limits=FetchLimits(timeout_seconds=0.01),
            transport=transport,
        )
        try:
            with pytest.raises(WebFetchRefusedError) as captured:
                await service.fetch(WebFetchCommand("https://example.test/slow"))
            assert captured.value.code is FetchErrorCode.TIMEOUT
        finally:
            await service.aclose()

    anyio.run(drive)


def test_ipv6_literal_is_canonicalized_with_brackets() -> None:
    target = normalize_url("https://[2606:4700:4700::1111]/dns-query")
    assert target.url == "https://[2606:4700:4700::1111]/dns-query"


def test_proxy_destination_hook_rejects_private_endpoint() -> None:
    async def drive() -> None:
        service = HardenedFetchService(resolver=lambda _host, _port: ["10.0.0.7"])
        try:
            with pytest.raises(SSRFBlockedError):
                service.validate_proxy_destination("http://proxy.example.test:8080")
        finally:
            await service.aclose()

    anyio.run(drive)
