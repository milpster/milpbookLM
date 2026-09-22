"""
Pinned-connection transport: the dedicated fetch transport (guide/11 Fetching).

A plain httpx/requests client performs a SECOND, uncontrolled DNS lookup inside
the OS socket layer after any user-space validation, which is exactly the race
a DNS-rebinding attack needs. This module removes that second lookup: the
network backend resolves every host through the (injectable) resolver,
validates EVERY candidate address, and hands the underlying connector a
NUMERIC address to dial. HTTP ``Host`` and TLS SNI/certificate verification
keep using the original, already-validated hostname (httpcore takes the SNI
from the request origin, not from the dial address).

Because the backend is the only connect path of the pool, EVERY connection
through the transport — first hop, every redirect hop, and proxy connects —
passes the same validation. A proxy destination configured on the service is
therefore enforced by the identical checks (guide/19: "Proxy deployments
apply the equivalent destination enforcement").
"""

from __future__ import annotations

import logging
import ssl
from collections.abc import AsyncIterator, Iterable
from typing import Protocol, runtime_checkable

import httpcore
import httpx
from httpcore import AsyncNetworkBackend, AsyncNetworkStream
from httpcore._backends.anyio import AnyIOBackend

from .addressing import AddressResolver, select_pinned_address

logger = logging.getLogger(__name__)


class _InnerBackend(Protocol):
    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> AsyncNetworkStream: ...

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> AsyncNetworkStream: ...

    async def sleep(self, seconds: float) -> None: ...


class ValidatingNetworkBackend(AsyncNetworkBackend):
    """Validate every connection target before the real connector dials it."""

    def __init__(
        self,
        inner: _InnerBackend,
        resolver: AddressResolver,
    ) -> None:
        """Wrap the real connector with the resolve-validate-pin step."""
        self._inner: _InnerBackend = inner
        self._resolver: AddressResolver = resolver

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> AsyncNetworkStream:
        """Raise before any socket exists when the target is not public."""
        pinned = select_pinned_address(host, port, resolver=self._resolver)
        if pinned != host:
            logger.debug("pinned fetch connection: host=%s -> %s", host, pinned)
        return await self._inner.connect_tcp(
            pinned,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> AsyncNetworkStream:
        """UNIX sockets are outside this transport's policy; they are not used."""
        raise httpcore.UnsupportedProtocol("unix sockets are not allowed")

    async def sleep(self, seconds: float) -> None:
        """Delegate retry sleep to the inner backend."""
        await self._inner.sleep(seconds)


@runtime_checkable
class _ClosableAsyncStream(Protocol):
    def __aiter__(self) -> AsyncIterator[bytes]: ...

    async def aclose(self) -> None: ...


class _ResponseStream(httpx.AsyncByteStream):
    """Adapt the httpcore response stream to the httpx byte-stream interface."""

    def __init__(self, httpcore_stream: _ClosableAsyncStream) -> None:
        self._stream: _ClosableAsyncStream = httpcore_stream

    async def __aiter__(self) -> AsyncIterator[bytes]:
        try:
            async for part in self._stream:
                yield part
        except httpcore.TimeoutException as exc:
            raise httpx.TimeoutException(str(exc)) from exc
        except httpcore.NetworkError as exc:
            raise httpx.NetworkError(str(exc)) from exc
        except httpcore.ProtocolError as exc:
            raise httpx.ProtocolError(str(exc)) from exc

    async def aclose(self) -> None:
        await self._stream.aclose()


class PinnedFetchTransport(httpx.AsyncBaseTransport):
    """The ONLY transport used for outbound fetches; no unmodified client path."""

    def __init__(
        self,
        *,
        resolver: AddressResolver,
        verify: bool = True,
        max_connections: int = 10,
        network_backend: AsyncNetworkBackend | None = None,
    ) -> None:
        """Build the pool whose every connection is pinned to a validated address."""
        self._resolver: AddressResolver = resolver
        context = ssl.create_default_context()
        if not verify:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        if network_backend is None:
            backend = ValidatingNetworkBackend(AnyIOBackend(), resolver)
        else:
            backend = ValidatingNetworkBackend(network_backend, resolver)
        self._pool: httpcore.AsyncConnectionPool = httpcore.AsyncConnectionPool(
            ssl_context=context if verify else None,
            max_connections=max_connections,
            http1=True,
            http2=False,
            network_backend=backend,
        )

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Route one request through the validating pool (no redirect following)."""
        req = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions=request.extensions,
        )
        try:
            resp = await self._pool.handle_async_request(req)
        except httpcore.TimeoutException as exc:
            raise httpx.TimeoutException(str(exc), request=request) from exc
        except httpcore.NetworkError as exc:
            raise httpx.NetworkError(str(exc), request=request) from exc
        except httpcore.ProtocolError as exc:
            raise httpx.ProtocolError(str(exc), request=request) from exc
        if not isinstance(resp.stream, _ClosableAsyncStream):
            raise httpx.StreamError("httpcore returned a non-closeable response stream")
        return httpx.Response(
            status_code=resp.status,
            headers=resp.headers,
            stream=_ResponseStream(resp.stream),
            extensions=resp.extensions,
        )

    async def aclose(self) -> None:
        """Close the pool and all pooled connections."""
        await self._pool.aclose()
