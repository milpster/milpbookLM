"""API dependency container: the wired ports + use cases shared by the routers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import Request
from milpbooklm_application.authn import LoginUser, LogoutUser, RegisterUser, RotateSession
from milpbooklm_application.chat import (
    ConversationStore,
    GenerateChatTurn,
    GenerateNotebookOverview,
)
from milpbooklm_application.grounding import GroundingStore
from milpbooklm_application.indexing import IndexBuildConfig
from milpbooklm_application.job_usecases import JobPorts
from milpbooklm_application.policy_engine import PolicyEngine
from milpbooklm_application.ports import (
    AuditLog,
    Clock,
    NotebookCustodyStore,
    NotebookReader,
    NotebookStore,
    SessionTokenStore,
    UserRepository,
)
from milpbooklm_application.retrieval import RetrieveChunks

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
    # UI-01: notebook creation (None = the create endpoint answers 503).
    notebook_store: NotebookStore | None = None
    jobs: JobPorts | None = None
    # IDX-01: retrieval (None = search endpoint answers 503) + the build config
    # used to enqueue index jobs on activation (None = indexing disabled).
    retrieval: RetrieveChunks | None = None
    index_config: IndexBuildConfig | None = None
    grounding: GroundingStore | None = None
    conversations: ConversationStore | None = None
    chat_turn: GenerateChatTurn | None = None
    notebook_overview: GenerateNotebookOverview | None = None


PrincipalDependency = Callable[[Request], Awaitable[Principal]]
