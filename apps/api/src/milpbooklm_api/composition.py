"""
Composition root: wire use cases to adapters and build the API app.

``build_app`` is the test/QA seam (explicit ports); ``create_app`` is the
production entry point (typed environment config + PostgreSQL). ``build_create_notebook``
is the earlier skeleton wiring, kept for the existing unit tests.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, Request
from milpbooklm_adapters.db.connections import make_engine
from milpbooklm_adapters.notebook_repository import InMemoryNotebookRepository
from milpbooklm_adapters.security.argon2 import Argon2PasswordHasher
from milpbooklm_adapters.security.clock import SystemClock
from milpbooklm_adapters.security.custody_store import PgNotebookCustodyStore
from milpbooklm_adapters.security.notebook_reader import PgNotebookReader
from milpbooklm_adapters.security.pg_identity import PgAuditLog, PgUserRepository
from milpbooklm_adapters.security.session_store import PgSessionTokenStore
from milpbooklm_application.authn import LoginUser, LogoutUser, RegisterUser, RotateSession
from milpbooklm_application.create_notebook import CreateNotebook
from milpbooklm_application.policy_engine import PolicyEngine
from milpbooklm_application.ports import (
    AuditLog,
    Clock,
    NotebookCustodyStore,
    NotebookReader,
    PasswordHasher,
    SessionTokenStore,
    UserRepository,
)
from starlette import status

from .auth_routes import build_auth_router
from .config_loader import load_config
from .deps import ApiDeps
from .notebook_routes import build_notebook_router
from .security import (
    CsrfOriginMiddleware,
    Principal,
    SecuritySettings,
    SlidingWindowLimiter,
    principal_from_request,
)


def build_create_notebook() -> tuple[CreateNotebook, InMemoryNotebookRepository]:
    """Return a ready-to-use use case and its repository (deterministic fake)."""
    repository = InMemoryNotebookRepository()
    return CreateNotebook(), repository


def build_app(
    *,
    users: UserRepository,
    hasher: PasswordHasher,
    sessions: SessionTokenStore,
    custody: NotebookCustodyStore,
    audit: AuditLog,
    notebooks: NotebookReader,
    settings: SecuritySettings,
    clock: Clock,
) -> FastAPI:
    """Build the API app from wired ports (the test/QA seam)."""
    app = FastAPI(title="MilpBook LM API")
    app.add_middleware(
        CsrfOriginMiddleware,
        settings=settings,
        sessions=sessions,
        users=users,
        clock=clock,
    )
    deps = ApiDeps(
        users=users,
        sessions=sessions,
        register=RegisterUser(users, hasher),
        login=LoginUser(users, hasher, sessions, clock, settings.session_ttl),
        rotate=RotateSession(sessions, clock, settings.session_ttl),
        logout=LogoutUser(sessions, clock),
        custody=custody,
        audit=audit,
        notebooks=notebooks,
        engine=PolicyEngine(),
        settings=settings,
        clock=clock,
        login_limiter=SlidingWindowLimiter(
            clock, settings.login_max_attempts, settings.login_window
        ),
        register_limiter=SlidingWindowLimiter(
            clock, settings.register_max_attempts, settings.register_window
        ),
    )
    app.state.deps = deps

    async def principal(request: Request) -> Principal:
        """Resolve the session cookie to a principal, or reject the request with 401."""
        resolved = principal_from_request(
            request,
            sessions=sessions,
            users=users,
            secret_key=settings.secret_key,
            clock=clock,
        )
        if resolved is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="authentication required",
            )
        return resolved

    app.include_router(build_auth_router(deps, principal))
    app.include_router(build_notebook_router(deps, principal))
    return app


def create_app() -> FastAPI:
    """Build the production app from the environment (typed config + PG app DSN)."""
    installation = load_config(os.environ).installation
    engine = make_engine(installation.database_url.get_secret_value())
    clock = SystemClock()
    settings = SecuritySettings(
        secret_key=installation.secret_key.get_secret_value(),
        base_url=installation.base_url,
    )
    return build_app(
        users=PgUserRepository(engine),
        hasher=Argon2PasswordHasher(),
        sessions=PgSessionTokenStore(engine, secret_key=settings.secret_key, clock=clock),
        custody=PgNotebookCustodyStore(engine),
        audit=PgAuditLog(engine),
        notebooks=PgNotebookReader(engine),
        settings=settings,
        clock=clock,
    )
