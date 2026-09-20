"""
HTTP observability + security-baseline middleware (ch18/19, FND-07).

Two focused middlewares:

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
"""

from __future__ import annotations

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
from starlette.responses import Response

REQUEST_ID_HEADER = "x-request-id"
TRACEPARENT_HEADER = "traceparent"

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


class CorrelationMiddleware(BaseHTTPMiddleware):
    """Bind one validated correlation/trace identity per request (ch18)."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Validate inbound ids, bind the context, echo the effective ids."""
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
        ctx = CorrelationContext(
            request_id=inbound.request_id,
            trace_id=trace_id,
            span_id=span_id,
            trace_flags=trace_flags,
        )
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
        response.headers["content-security-policy"] = _CONTENT_SECURITY_POLICY
        response.headers["x-content-type-options"] = "nosniff"
        response.headers["referrer-policy"] = "no-referrer"
        response.headers["permissions-policy"] = _PERMISSIONS_POLICY
        return response
