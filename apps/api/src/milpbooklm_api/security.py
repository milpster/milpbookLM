"""
API security services.

Session cookie discipline (Secure/HttpOnly/SameSite=Lax, rotated at login and
on privilege change) plus CSRF validation on unsafe methods (ch17 §7).
Unsafe methods under /api/v1 accept any Origin — the installation is reached
from LAN hosts and forwarded WAN ports, so an origin allowlist cannot
enumerate the possible origins. The remaining cross-origin defense: when a
request carries a live session cookie it must also carry the stateless CSRF
token (HMAC-derived from the session token, so validation needs no storage
round-trip).
"""

from __future__ import annotations

import hmac
import math
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Request
from milpbooklm_adapters.security.session_store import derive_csrf_token
from milpbooklm_application.authn import DEFAULT_SESSION_TTL
from milpbooklm_application.ports import Clock, SessionTokenStore, UserRepository
from milpbooklm_domain.identity import User
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

SESSION_COOKIE = "mb_session"
CSRF_HEADER = "x-csrf-token"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
API_PREFIX = "/api/v1"


@dataclass(frozen=True, slots=True)
class SecuritySettings:
    """Deployment-wide security settings for the API."""

    secret_key: str
    base_url: str
    session_ttl: timedelta = DEFAULT_SESSION_TTL
    login_max_attempts: int = 5
    login_window: timedelta = timedelta(minutes=15)
    register_max_attempts: int = 3
    register_window: timedelta = timedelta(hours=1)


@dataclass(frozen=True, slots=True)
class Principal:
    """The authenticated request principal (resolved once per request)."""

    user: User
    session_id: uuid.UUID
    token: str
    csrf_token: str


class SlidingWindowLimiter:
    """In-memory sliding-window rate limiter (wave 2: PG-backed durable limiter)."""

    def __init__(self, clock: Clock, max_events: int, window: timedelta) -> None:
        """Wire the clock and the window shape."""
        self._clock = clock
        self._max_events = max_events
        self._window = window
        self._events: dict[str, deque[float]] = {}

    def allow(self, key: str) -> bool:
        """Record an attempt; return False when the window is already full."""
        now = self._clock.now().timestamp()
        cutoff = now - self._window.total_seconds()
        events = self._events.setdefault(key, deque())
        while events and events[0] <= cutoff:
            events.popleft()
        if len(events) >= self._max_events:
            return False
        events.append(now)
        return True

    def retry_after_seconds(self, key: str) -> int:
        """Whole seconds until the oldest recorded event leaves the window."""
        now = self._clock.now().timestamp()
        window_seconds = self._window.total_seconds()
        events = self._events.get(key)
        if not events:
            return int(window_seconds)
        return max(1, math.ceil(events[0] + window_seconds - now))


def principal_from_request(
    request: Request,
    *,
    sessions: SessionTokenStore,
    users: UserRepository,
    secret_key: str,
    clock: Clock,
) -> Principal | None:
    """Resolve the session cookie to a live Principal, or None (caller maps to 401)."""
    token = request.cookies.get(SESSION_COOKIE, "")
    if not token:
        return None
    resolved = sessions.authenticate(token, now=clock.now())
    if resolved is None:
        return None
    session_id, user_id = resolved
    user = users.get(user_id)
    if user is None or not user.enabled:
        return None
    return Principal(
        user=user,
        session_id=session_id,
        token=token,
        csrf_token=derive_csrf_token(secret_key, token),
    )


def set_session_cookie(response: Response, token: str, *, ttl: timedelta) -> None:
    """Apply the cookie discipline to a session-issuing response."""
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(ttl.total_seconds()),
        secure=True,
        httponly=True,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    """Clear the session cookie with the same flags it was set with."""
    response.delete_cookie(SESSION_COOKIE, secure=True, httponly=True, samesite="lax", path="/")


class CsrfOriginMiddleware(BaseHTTPMiddleware):
    """CSRF enforcement for unsafe methods under the API prefix (origins are unrestricted)."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        settings: SecuritySettings,
        sessions: SessionTokenStore,
        users: UserRepository,
        clock: Clock,
    ) -> None:
        """Wire the middleware around the app with the enforcement dependencies."""
        super().__init__(app)
        self._settings = settings
        self._sessions = sessions
        self._users = users
        self._clock = clock

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> JSONResponse | Response:
        """Enforce CSRF on unsafe methods with a live session (origins are unrestricted)."""
        if request.method in UNSAFE_METHODS and request.url.path.startswith(API_PREFIX):
            principal = principal_from_request(
                request,
                sessions=self._sessions,
                users=self._users,
                secret_key=self._settings.secret_key,
                clock=self._clock,
            )
            if principal is not None:
                presented = request.headers.get(CSRF_HEADER, "")
                if not presented.isascii() or not hmac.compare_digest(
                    presented, principal.csrf_token
                ):
                    return JSONResponse(
                        status_code=403, content={"detail": {"reason": "csrf_rejected"}}
                    )
        return await call_next(request)
