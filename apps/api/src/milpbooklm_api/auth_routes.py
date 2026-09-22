"""
Authentication routes: register, login, logout, rotate, me.

Enumeration resistance is structural: every login failure (unknown email, bad
password, disabled account) is the same uniform 401 body; rate limiting emits one
uniform 409-free 429 body per key class.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from milpbooklm_adapters.security.session_store import derive_csrf_token
from milpbooklm_application.audit_actions import AuditAction
from milpbooklm_application.authn import RegistrationError
from milpbooklm_domain.telemetry import current_context
from pydantic import BaseModel, ConfigDict
from starlette import status

from .deps import ApiDeps, PrincipalDependency
from .security import Principal, clear_session_cookie, set_session_cookie

logger = logging.getLogger(__name__)


class RegisterRequest(BaseModel):
    """The registration body (the use case validates shape and policy)."""

    model_config = ConfigDict(frozen=True)

    email: str
    display_name: str
    password: str


class LoginRequest(BaseModel):
    """The login body (the use case keeps failure outcomes uniform)."""

    model_config = ConfigDict(frozen=True)

    email: str
    password: str


def _client_host(request: Request) -> str:
    """Return the client IP for limiter keys ('unknown' when unresolvable)."""
    return request.client.host if request.client is not None else "unknown"


def _too_many(retry_after_seconds: int) -> HTTPException:
    """Return the uniform rate-limit rejection (identical for every limiter key)."""
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={"reason": "rate_limited", "retry_after_seconds": retry_after_seconds},
        headers={"Retry-After": str(retry_after_seconds)},
    )


def _login_response(deps: ApiDeps, email: str, password: str) -> JSONResponse:
    """Build the login JSON response (uniform 401 on any failure)."""
    ctx = current_context()
    request_id = ctx.request_id if ctx is not None else None
    email_norm = email.strip().lower()
    outcome = deps.login(email, password)
    if not outcome.succeeded:
        deps.audit.record(
            actor_id=None,
            action=AuditAction.LOGIN_FAILED,
            subject_kind="user",
            details={"email": email_norm, "outcome": "invalid_credentials"},
            request_id=request_id,
        )
        logger.info("login failed", extra={"email": email_norm})
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "invalid credentials"},
        )
    session = outcome.session
    if session is None or outcome.user_id is None:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "internal"},
        )
    deps.audit.record(
        actor_id=outcome.user_id,
        action=AuditAction.LOGIN_SUCCEEDED,
        subject_kind="user",
        subject_id=outcome.user_id,
        details={"email": email_norm},
        request_id=request_id,
    )
    logger.info("login succeeded", extra={"user_id": str(outcome.user_id)})
    csrf = derive_csrf_token(deps.settings.secret_key, session.token)
    response = JSONResponse(content={"user_id": str(outcome.user_id), "csrf_token": csrf})
    set_session_cookie(response, session.token, ttl=deps.settings.session_ttl)
    return response


def build_auth_router(deps: ApiDeps, principal: PrincipalDependency) -> APIRouter:
    """Build the /api/v1/auth router over the wired dependencies."""
    router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

    @router.post("/register", status_code=201)
    async def register(body: RegisterRequest, request: Request) -> dict[str, str]:
        """Create a local account (rate-limited per client IP)."""
        key = f"register:{_client_host(request)}"
        if not deps.register_limiter.allow(key):
            raise _too_many(deps.register_limiter.retry_after_seconds(key))
        try:
            user_id = deps.register(body.email, body.display_name, body.password)
        except RegistrationError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=str(exc)
            ) from exc
        return {"user_id": str(user_id)}

    @router.post("/login")
    async def login(body: LoginRequest, request: Request) -> JSONResponse:
        """Authenticate (uniform 401 on any failure; rate-limited per IP+account)."""
        key = f"login:{_client_host(request)}:{body.email.strip().lower()}"
        if not deps.login_limiter.allow(key):
            raise _too_many(deps.login_limiter.retry_after_seconds(key))
        return _login_response(deps, body.email, body.password)

    @router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
    async def logout(principal: Principal = Depends(principal)) -> Response:
        """Revoke the presented session and clear the cookie."""
        deps.logout(principal.token)
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        clear_session_cookie(response)
        return response

    @router.post("/rotate")
    async def rotate(principal: Principal = Depends(principal)) -> JSONResponse:
        """Rotate the session token (privilege change); new cookie + new CSRF token."""
        new_session = deps.rotate(principal.token)
        if new_session is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid session"
            )
        csrf = derive_csrf_token(deps.settings.secret_key, new_session.token)
        response = JSONResponse(content={"csrf_token": csrf})
        set_session_cookie(response, new_session.token, ttl=deps.settings.session_ttl)
        return response

    @router.get("/me")
    async def me(principal: Principal = Depends(principal)) -> dict[str, object]:
        """Return the authenticated account (no password material)."""
        return {
            "user_id": str(principal.user.id),
            "email": principal.user.email,
            "display_name": principal.user.display_name,
            "status": principal.user.status.value,
            "installation_admin": principal.user.installation_admin,
        }

    return router
