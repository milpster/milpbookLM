"""
HTTP observability + security-baseline middleware (ch18/19, FND-07).

Three focused middlewares:

* :class:`CorrelationMiddleware` validates inbound ``X-Request-Id`` /
  ``traceparent`` headers (unparseable bytes are dropped, never reflected),
  binds the correlation context for the request task so structured logs and
  job enqueue share one identity, and echoes the effective ids back in the
  response headers.
* :class:`SecurityHeadersMiddleware` applies the deployment security
  baseline to every response: an app-origin Content-Security-Policy with
  ``frame-ancestors 'none'``, MIME-sniffing refusal, referrer policy and a
  minimal Permissions-Policy. CORS is OFF by default: the API is consumed
  same-origin by its own UI; no CORSMiddleware is registered anywhere.
* :class:`UnhandledErrorMiddleware` (registered outermost) turns any
  unhandled exception into a uniform 500 that still carries the correlation
  + security header baseline, because the framework's own ``Exception``
  handler path (ServerErrorMiddleware) sits outside the user middlewares and
  would emit a bare 500 with none of those headers.
"""

from __future__ import annotations

import logging

from fastapi import Request
from milpbooklm_domain.telemetry import (
    CorrelationContext,
    bind_context,
    context_from_request,
    format_traceparent,
    new_span_id,
    new_trace_id,
    reset_context,
)
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "x-request-id"
TRACEPARENT_HEADER = "traceparent"
_CORRELATION_STATE_ATTR = "_milpbooklm_effective_correlation"
type _EffectiveCorrelation = tuple[CorrelationContext, str, str, str]

# App-origin CSP: only our own assets, no framing, no base/form escapes.
_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data:; "
    "media-src 'self'; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)
_PERMISSIONS_POLICY = (
    "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
)


def _apply_security_headers(response: Response) -> None:
    """Attach the deployment security-header baseline to one response."""
    response.headers["content-security-policy"] = _CONTENT_SECURITY_POLICY
    response.headers["x-content-type-options"] = "nosniff"
    response.headers["referrer-policy"] = "no-referrer"
    response.headers["permissions-policy"] = _PERMISSIONS_POLICY


def _inbound_context(request: Request) -> _EffectiveCorrelation:
    """
    Validate inbound ids, starting a fresh sampled trace when absent (ch18).

    Returns the bound context plus its trace values as proven-non-None strings
    (the echo headers need them; the context fields are ``str | None``).
    """
    inbound = context_from_request(
        request_id=request.headers.get(REQUEST_ID_HEADER),
        traceparent=request.headers.get(TRACEPARENT_HEADER),
    )
    trace_id = inbound.trace_id
    span_id = inbound.span_id
    trace_flags = inbound.trace_flags
    if trace_id is None or span_id is None or trace_flags is None:
        # No complete inbound trace: start a fresh sampled trace.
        trace_id = new_trace_id()
        span_id = new_span_id()
        trace_flags = "01"
    return (
        CorrelationContext(
            request_id=inbound.request_id,
            trace_id=trace_id,
            span_id=span_id,
            trace_flags=trace_flags,
        ),
        trace_id,
        span_id,
        trace_flags,
    )


class CorrelationMiddleware(BaseHTTPMiddleware):
    """Bind one validated correlation/trace identity per request (ch18)."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Validate inbound ids, bind the context, echo the effective ids."""
        effective = _inbound_context(request)
        setattr(request.state, _CORRELATION_STATE_ATTR, effective)
        ctx, trace_id, span_id, trace_flags = effective
        token = bind_context(ctx)
        try:
            response = await call_next(request)
        finally:
            reset_context(token)
        response.headers[REQUEST_ID_HEADER] = ctx.request_id
        response.headers[TRACEPARENT_HEADER] = format_traceparent(trace_id, span_id, trace_flags)
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Apply the deployment security-header baseline to every response (ch19)."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Attach the security baseline headers to the downstream response."""
        response = await call_next(request)
        _apply_security_headers(response)
        return response


class UnhandledErrorMiddleware:
    """
    Turn any unhandled exception into a uniform 500 that keeps the baseline.

    Plain ASGI (not BaseHTTPMiddleware), registered outermost. The framework's
    own ``Exception`` handler runs in ServerErrorMiddleware, which sits OUTSIDE
    the user middlewares, so a 500 emitted there would lack the correlation and
    security headers; intercepting here is the only central point where a 500
    can carry them. The body is uniform (no exception detail is ever reflected)
    and the error is logged inside the bound correlation context, so the log
    line and the response share one request id.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Wrap the downstream ASGI app."""
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Serve the request; any unhandled exception becomes the uniform 500."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        response_started = False

        async def sending(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self._app(scope, receive, sending)
        except Exception as exc:
            if response_started:
                # Bytes already on the wire: nothing coherent left to send.
                raise
            request = Request(scope, receive, send)
            effective: _EffectiveCorrelation | None = getattr(
                request.state, _CORRELATION_STATE_ATTR, None
            )
            if effective is None:
                effective = _inbound_context(request)
            ctx, trace_id, span_id, trace_flags = effective
            token = bind_context(ctx)
            try:
                logger.error(
                    "unhandled request error",
                    exc_info=exc,
                    extra={"method": scope["method"], "path": str(scope["path"])},
                )
                response = JSONResponse(
                    status_code=500, content={"detail": "internal"}
                )
                response.headers[REQUEST_ID_HEADER] = ctx.request_id
                response.headers[TRACEPARENT_HEADER] = format_traceparent(
                    trace_id, span_id, trace_flags
                )
                _apply_security_headers(response)
                await response(scope, receive, send)
            finally:
                reset_context(token)
