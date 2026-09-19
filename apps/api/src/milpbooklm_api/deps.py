"""API dependency container: the wired ports + use cases shared by the routers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import Request
from milpbooklm_application.authn import LoginUser, LogoutUser, RegisterUser, RotateSession
from milpbooklm_application.policy_engine import PolicyEngine
from milpbooklm_application.ports import (
    AuditLog,
    Clock,
    NotebookCustodyStore,
    NotebookReader,
    SessionTokenStore,
    UserRepository,
)

from .security import Principal, SecuritySettings, SlidingWindowLimiter


@dataclass(frozen=True, slots=True)
class ApiDeps:
    """Everything the API routers need (wired once at the composition root)."""

    users: UserRepository
    sessions: SessionTokenStore
    register: RegisterUser
    login: LoginUser
    rotate: RotateSession
    logout: LogoutUser
    custody: NotebookCustodyStore
    audit: AuditLog
    notebooks: NotebookReader
    engine: PolicyEngine
    settings: SecuritySettings
    clock: Clock
    login_limiter: SlidingWindowLimiter
    register_limiter: SlidingWindowLimiter


PrincipalDependency = Callable[[Request], Awaitable[Principal]]
