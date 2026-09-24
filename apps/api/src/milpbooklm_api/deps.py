"""API dependency container: the wired ports + use cases shared by the routers."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import Request
from milpbooklm_application.artifact_core import ArtifactStore
from milpbooklm_application.artifact_export import ExportArtifact
from milpbooklm_application.artifact_lifecycle import (
    CancelArtifact,
    CreateArtifact,
    EditArtifact,
    GenerateArtifact,
    MarkOutOfDate,
    RegenerateArtifact,
)
from milpbooklm_application.artifact_study import (
    GetStudyState,
    SnapshotStudySession,
    UpdateStudyState,
)
from milpbooklm_application.authn import LoginUser, LogoutUser, RegisterUser, RotateSession
from milpbooklm_application.chat import (
    ConversationStore,
    GenerateChatTurn,
    GenerateNotebookOverview,
)
from milpbooklm_application.grounding import GroundingStore
from milpbooklm_application.indexing import IndexBuildConfig
from milpbooklm_application.job_usecases import JobPorts
from milpbooklm_application.note_core import NoteStore
from milpbooklm_application.note_lifecycle import (
    CreateNote,
    EditNote,
    PromoteNoteToSource,
    SaveResponseToNote,
    TransformNotes,
)
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
from milpbooklm_application.research import (
    CancelResearchRun,
    CreateResearchRun,
    PauseResearchRun,
    ResearchRunStore,
    ResumeResearchRun,
    StartResearchRun,
)
from milpbooklm_application.retrieval import RetrieveChunks

from .security import ActiveUsersTracker, Principal, SecuritySettings, SlidingWindowLimiter


@dataclass(frozen=True, slots=True)
class ResearchRunDeps:
    """The wired research run surface (routes answer 503 when absent)."""

    store: ResearchRunStore
    create: CreateResearchRun
    start: StartResearchRun
    pause: PauseResearchRun
    resume: ResumeResearchRun
    cancel: CancelResearchRun


@dataclass(frozen=True, slots=True)
class ArtifactDeps:
    """The wired studio artifact surface (routes answer 503 when absent)."""

    store: ArtifactStore
    create: CreateArtifact
    generate: GenerateArtifact
    edit: EditArtifact
    regenerate: RegenerateArtifact
    cancel: CancelArtifact
    mark_out_of_date: MarkOutOfDate
    export: ExportArtifact
    update_state: UpdateStudyState
    get_state: GetStudyState
    snapshot: SnapshotStudySession


@dataclass(frozen=True, slots=True)
class NoteDeps:
    """The wired immutable-note workflow surface."""

    store: NoteStore
    create: CreateNote
    edit: EditNote
    save_response: SaveResponseToNote
    transform: TransformNotes
    promote: PromoteNoteToSource


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
    active_users: ActiveUsersTracker
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
    research: ResearchRunDeps | None = None
    artifacts: ArtifactDeps | None = None
    notes: NoteDeps | None = None
    seed_onboarding: Callable[[uuid.UUID], None] | None = None


PrincipalDependency = Callable[[Request], Awaitable[Principal]]
