"""
Composition root: wire use cases to adapters and build the API app.

``build_app`` is the test/QA seam (explicit ports); ``create_app`` is the
production entry point (typed environment config + PostgreSQL). ``build_create_notebook``
is the earlier skeleton wiring, kept for the existing unit tests.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import assert_never

import sqlalchemy as sa
from fastapi import FastAPI, HTTPException, Request
from milpbooklm_adapters.artifact_export import PgExportAuthorizer
from milpbooklm_adapters.artifact_store import PgArtifactStore
from milpbooklm_adapters.blobs import FilesystemBlobStore, PgBlobRepository
from milpbooklm_adapters.chat import PgConversationStore
from milpbooklm_adapters.db.connections import make_engine
from milpbooklm_adapters.fetch import HardenedFetchService
from milpbooklm_adapters.grounding import PgGroundingStore
from milpbooklm_adapters.grounding_completion import (
    FakeGroundingCompletionProvider,
    LlamaCppCompletionProvider,
)
from milpbooklm_adapters.indexing import PgRetrievalService
from milpbooklm_adapters.jobs import PgJobRepository, PgOutboxDispatcher, PolicyAuthzRevalidator
from milpbooklm_adapters.models.embedding_client import LlamaCppEmbeddingClient
from milpbooklm_adapters.note_store import PgNoteStore
from milpbooklm_adapters.note_transform import (
    FakeNoteTransformProvider,
    LlamaCppNoteTransformProvider,
)
from milpbooklm_adapters.notebook_repository import InMemoryNotebookRepository
from milpbooklm_adapters.provider_health import ProviderHealth
from milpbooklm_adapters.research_runs import PgResearchRunStore
from milpbooklm_adapters.security.argon2 import Argon2PasswordHasher
from milpbooklm_adapters.security.clock import SystemClock
from milpbooklm_adapters.security.custody_store import PgNotebookCustodyStore
from milpbooklm_adapters.security.notebook_reader import PgNotebookReader
from milpbooklm_adapters.security.notebook_store import PgNotebookStore
from milpbooklm_adapters.security.pg_identity import (
    PgAuditLog,
    PgUserRepository,
    display_names,
)
from milpbooklm_adapters.security.session_store import PgSessionTokenStore
from milpbooklm_adapters.sources import FilesystemQuarantineStore, PgSourceCatalog, PgSourcePurge
from milpbooklm_application.artifact_export import ExportArtifact
from milpbooklm_application.artifact_lifecycle import (
    CancelArtifact,
    CreateArtifact,
    EditArtifact,
    GenerateArtifact,
    MarkOutOfDate,
    RegenerateArtifact,
)
from milpbooklm_application.artifact_recipes import build_recipe_registry
from milpbooklm_application.artifact_study import (
    GetStudyState,
    SnapshotStudySession,
    UpdateStudyState,
)
from milpbooklm_application.authn import LoginUser, LogoutUser, RegisterUser, RotateSession
from milpbooklm_application.capabilities import CapabilityRuntime
from milpbooklm_application.chat import GenerateChatTurn, GenerateNotebookOverview
from milpbooklm_application.create_notebook import CreateNotebook
from milpbooklm_application.grounding import GenerateGroundedAnswer
from milpbooklm_application.indexing import (
    DEFAULT_EMBEDDING_NORMALIZATION,
    EmbeddingSpec,
    IndexBuildConfig,
)
from milpbooklm_application.job_capacity import load_capacity_policy
from milpbooklm_application.job_usecases import (
    CancelJob,
    CompleteJob,
    EnqueueJob,
    JobPorts,
    RecoverExpiredLeases,
)
from milpbooklm_application.note_lifecycle import (
    CreateNote,
    EditNote,
    PromoteNoteToSource,
    SaveResponseToNote,
    TransformNotes,
)
from milpbooklm_application.onboarding import SeedFeatureGuide
from milpbooklm_application.policy_engine import PolicyEngine
from milpbooklm_application.ports import (
    AuditLog,
    Clock,
    NotebookCustodyStore,
    NotebookReader,
    NotebookStore,
    PasswordHasher,
    SessionTokenStore,
    UserRepository,
)
from milpbooklm_application.public_video import AcquirePublicVideo
from milpbooklm_application.research import (
    CancelResearchRun,
    CreateResearchRun,
    PauseResearchRun,
    ResumeResearchRun,
    StartResearchRun,
)
from milpbooklm_application.retrieval import RetrieveChunks
from milpbooklm_application.source_acquisition import AcquireSource, SourceCatalog
from milpbooklm_application.source_lifecycle import NoOpBackupExpiryScheduler, SourcePurge
from milpbooklm_application.structured_logging import configure_structured_logging
from milpbooklm_application.web_fetch import AcquireWebSource
from milpbooklm_domain.capabilities import CapabilityDefinition, DependencyId, FeatureFlag
from milpbooklm_domain.indexing import STRUCTURAL_CHUNKER_V1
from starlette import status

from .artifact_routes import build_artifact_router
from .auth_routes import build_auth_router
from .capability_registry import load_capability_registry
from .capability_routes import build_capability_router
from .config import ChatProvider, InstallationConfig
from .config_loader import load_config
from .conversation_routes import build_conversation_router
from .deps import ApiDeps, ArtifactDeps, NoteDeps, ResearchRunDeps
from .grounding_routes import build_grounding_router
from .health_routes import (
    DeploymentHealth,
    ProbeOutcome,
    ServerComponents,
    ServerComponentStatus,
    build_health_router,
    probe_worker,
)
from .job_routes import JobActivity, build_job_router, job_activity
from .note_routes import build_note_router
from .notebook_overview_routes import build_notebook_overview_router
from .notebook_routes import build_notebook_router
from .observability import (
    CorrelationMiddleware,
    SecurityHeadersMiddleware,
    UnhandledErrorMiddleware,
)
from .research_routes import build_research_router
from .retrieval_routes import build_retrieval_router
from .security import (
    ActiveUsersTracker,
    CsrfOriginMiddleware,
    Principal,
    SecuritySettings,
    SlidingWindowLimiter,
    principal_from_request,
)
from .source_routes import build_source_router


def build_create_notebook() -> tuple[CreateNotebook, InMemoryNotebookRepository]:
    """Return a ready-to-use use case and its repository (deterministic fake)."""
    repository = InMemoryNotebookRepository()
    return CreateNotebook(), repository


def _completion_provider(
    provider: ChatProvider, health: ProviderHealth | None = None
) -> LlamaCppCompletionProvider | FakeGroundingCompletionProvider:
    match provider:
        case ChatProvider.LLAMA_CPP:
            return LlamaCppCompletionProvider(health=health)
        case ChatProvider.FAKE:
            return FakeGroundingCompletionProvider()
        case unreachable:
            assert_never(unreachable)


def _note_transform_provider(
    provider: ChatProvider, health: ProviderHealth | None = None
) -> LlamaCppNoteTransformProvider | FakeNoteTransformProvider:
    match provider:
        case ChatProvider.LLAMA_CPP:
            return LlamaCppNoteTransformProvider(health=health)
        case ChatProvider.FAKE:
            return FakeNoteTransformProvider()
        case unreachable:
            assert_never(unreachable)


def _configured_provider_ids(installation: InstallationConfig) -> frozenset[DependencyId]:
    """
    Map the actually-wired providers onto registry provider dependency ids.

    The composition always wires exactly one chat completion provider
    (llama_cpp or the deterministic fake) and, when an embedding endpoint is
    configured, one embedding client — so those registry dependencies are
    satisfied. Explicitly configured extra providers are unioned in.
    """
    providers = {
        DependencyId(provider) for provider in installation.configured_provider_capabilities
    }
    providers.add(DependencyId("chat_provider"))
    if installation.embedding_base_url is not None:
        providers.add(DependencyId("embedding_provider"))
    return frozenset(providers)


def build_app(
    *,
    users: UserRepository,
    hasher: PasswordHasher,
    sessions: SessionTokenStore,
    custody: NotebookCustodyStore,
    audit: AuditLog,
    notebooks: NotebookReader,
    notebook_store: NotebookStore | None = None,
    settings: SecuritySettings,
    clock: Clock,
    jobs: JobPorts | None = None,
    health: DeploymentHealth | None = None,
    capability_definitions: tuple[CapabilityDefinition, ...] | None = None,
    capability_runtime: CapabilityRuntime | None = None,
    source_acquisition: AcquireSource | None = None,
    source_catalog: SourceCatalog | None = None,
    web_source_acquisition: AcquireWebSource | None = None,
    public_video_acquisition: AcquirePublicVideo | None = None,
    source_purge: SourcePurge | None = None,
    retrieval: RetrieveChunks | None = None,
    index_config: IndexBuildConfig | None = None,
    grounding: PgGroundingStore | None = None,
    conversations: PgConversationStore | None = None,
    completion: LlamaCppCompletionProvider | FakeGroundingCompletionProvider | None = None,
    research: ResearchRunDeps | None = None,
    artifacts: ArtifactDeps | None = None,
    notes: NoteDeps | None = None,
    job_activity_provider: Callable[[], JobActivity] | None = None,
    seed_onboarding: Callable[[uuid.UUID], None] | None = None,
    server_components: ServerComponents | None = None,
) -> FastAPI:
    """Build the API app from wired ports (the test/QA seam)."""
    app = FastAPI(title="milpbookLM API")
    app.add_middleware(
        CsrfOriginMiddleware,
        settings=settings,
        sessions=sessions,
        users=users,
        clock=clock,
    )
    # Last added runs outermost: the 500 catch-all wraps correlation, which
    # wraps headers, which wrap CSRF.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CorrelationMiddleware)
    app.add_middleware(UnhandledErrorMiddleware)
    chat_turn = (
        GenerateChatTurn(
            conversations,
            GenerateGroundedAnswer(
                retrieval=retrieval,
                completion=completion or FakeGroundingCompletionProvider(),
                store=grounding,
            ),
        )
        if conversations is not None and retrieval is not None and grounding is not None
        else None
    )
    active_users = ActiveUsersTracker(clock)
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
        notebook_store=notebook_store,
        engine=PolicyEngine(),
        settings=settings,
        clock=clock,
        active_users=active_users,
        login_limiter=SlidingWindowLimiter(
            clock, settings.login_max_attempts, settings.login_window
        ),
        register_limiter=SlidingWindowLimiter(
            clock, settings.register_max_attempts, settings.register_window
        ),
        jobs=jobs,
        retrieval=retrieval,
        index_config=index_config,
        grounding=grounding,
        conversations=conversations,
        chat_turn=chat_turn,
        notebook_overview=(
            GenerateNotebookOverview(conversations, chat_turn)
            if conversations is not None and chat_turn is not None
            else None
        ),
        research=research,
        artifacts=artifacts,
        notes=notes,
        seed_onboarding=seed_onboarding,
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
        active_users.touch(resolved.user.id)
        return resolved

    definitions = (
        load_capability_registry() if capability_definitions is None else capability_definitions
    )
    runtime = CapabilityRuntime() if capability_runtime is None else capability_runtime
    app.include_router(build_health_router(health, principal, server_components))
    app.include_router(build_capability_router(definitions, runtime, health))
    app.include_router(build_auth_router(deps, principal))
    app.include_router(build_notebook_router(deps, principal))
    app.include_router(build_retrieval_router(deps, principal))
    app.include_router(build_grounding_router(deps, principal))
    app.include_router(build_conversation_router(deps, principal))
    app.include_router(build_notebook_overview_router(deps, principal))
    if jobs is not None:
        app.include_router(build_job_router(deps, principal, jobs, job_activity_provider))
    if research is not None:
        app.include_router(build_research_router(deps, principal, research))
    if artifacts is not None:
        app.include_router(build_artifact_router(deps, principal, artifacts))
    if notes is not None:
        app.include_router(build_note_router(deps, principal, notes))
    if source_acquisition is not None and source_catalog is not None:
        app.include_router(
            build_source_router(
                deps,
                principal,
                source_acquisition,
                source_catalog,
                acquire_web=web_source_acquisition,
                acquire_public_video=public_video_acquisition,
                purge=source_purge,
            )
        )
    return app


def build_job_ports(
    engine: sa.engine.Engine, users: UserRepository, notebooks: NotebookReader
) -> JobPorts:
    """Wire the durable job surface over the PostgreSQL adapters (ch15)."""
    repo = PgJobRepository(engine)
    dispatcher = PgOutboxDispatcher(engine)
    revalidator = PolicyAuthzRevalidator(engine, PolicyEngine(), users, notebooks)
    policy = load_capacity_policy(os.environ)
    return JobPorts(
        repo=repo,
        dispatcher=dispatcher,
        enqueue=EnqueueJob(repo, policy),
        cancel=CancelJob(repo),
        complete=CompleteJob(repo, revalidator),
        recover=RecoverExpiredLeases(repo),
    )


def _embedding_wiring(
    installation: InstallationConfig,
    health: ProviderHealth | None = None,
) -> tuple[IndexBuildConfig | None, LlamaCppEmbeddingClient | None]:
    """Return the IDX-01 embedding wiring (None pair = a lexical-only installation)."""
    if installation.embedding_base_url is None:
        return None, None
    base_url = installation.embedding_base_url
    model = installation.embedding_model or "bge-m3"
    dimension = installation.embedding_dimension or 1024
    config = IndexBuildConfig(
        profile=STRUCTURAL_CHUNKER_V1,
        embedding=EmbeddingSpec(
            model=model,
            model_ref=base_url,
            dimension=dimension,
            normalization=DEFAULT_EMBEDDING_NORMALIZATION,
        ),
    )
    return config, LlamaCppEmbeddingClient(base_url, model, health=health)


def create_app() -> FastAPI:
    """Build the production app from the environment (typed config + PG app DSN)."""
    configure_structured_logging()
    installation = load_config(os.environ).installation
    engine = make_engine(installation.database_url.get_secret_value())
    clock = SystemClock()
    settings = SecuritySettings(
        secret_key=installation.secret_key.get_secret_value(),
        base_url=installation.base_url,
        session_cookie_secure=installation.session_cookie_secure,
        login_max_attempts=installation.login_max_attempts,
        login_window=timedelta(minutes=installation.login_window_minutes),
        register_max_attempts=installation.register_max_attempts,
        register_window=timedelta(minutes=installation.register_window_minutes),
    )
    users = PgUserRepository(engine)
    notebooks = PgNotebookReader(engine)
    audit = PgAuditLog(engine)
    jobs = build_job_ports(engine, users, notebooks)
    source_catalog = PgSourceCatalog(engine)
    blob_store = FilesystemBlobStore(
        installation.blob_root,
        PgBlobRepository(engine),
        clock,
    )
    source_acquisition = AcquireSource(
        quarantine=FilesystemQuarantineStore(
            installation.blob_root,
            max_bytes=installation.max_acquisition_bytes,
        ),
        blobs=blob_store,
        catalog=source_catalog,
        audit=audit,
        jobs=jobs,
    )
    fetch_service = HardenedFetchService()
    web_source_acquisition = AcquireWebSource(
        fetch=fetch_service,
        acquire=source_acquisition,
        audit=audit,
    )
    # REFERENCE-DEPENDENCIES names no credential-free compliant public-video
    # adapter, so the adapter set ships empty: imports terminate in the
    # explicit transcript_unavailable state, never a fabricated transcript.
    public_video_acquisition = AcquirePublicVideo(catalog=source_catalog, audit=audit)
    # Provider health is the providers' own last-call evidence (no ad hoc
    # probing): the chat completion and note-transform providers share one
    # recorder because they hit the same local completion endpoint.
    chat_health = ProviderHealth(clock)
    embedding_health = ProviderHealth(clock)
    index_config, embedding_client = _embedding_wiring(installation, embedding_health)
    retrieval = RetrieveChunks(
        retrieval=PgRetrievalService(engine),
        embeddings=embedding_client,
        expected_dimension=(index_config.embedding.dimension if index_config is not None else None),
    )
    grounding = PgGroundingStore(engine)
    conversations = PgConversationStore(engine)
    research_store = PgResearchRunStore(engine)
    artifact_store = PgArtifactStore(engine)
    note_store = PgNoteStore(engine)
    notebook_store = PgNotebookStore(engine)
    artifact_registry = build_recipe_registry()
    artifacts = ArtifactDeps(
        store=artifact_store,
        create=CreateArtifact(artifact_store),
        generate=GenerateArtifact(artifact_store, artifact_registry, blob_store),
        edit=EditArtifact(artifact_store, artifact_registry, blob_store),
        regenerate=RegenerateArtifact(artifact_store, artifact_registry, blob_store),
        cancel=CancelArtifact(artifact_store),
        mark_out_of_date=MarkOutOfDate(artifact_store),
        export=ExportArtifact(
            artifact_store,
            PgExportAuthorizer(engine, users, notebooks, PolicyEngine()),
        ),
        update_state=UpdateStudyState(artifact_store),
        get_state=GetStudyState(artifact_store),
        snapshot=SnapshotStudySession(artifact_store),
    )
    notes = NoteDeps(
        store=note_store,
        create=CreateNote(note_store),
        edit=EditNote(note_store),
        save_response=SaveResponseToNote(note_store),
        transform=TransformNotes(
            note_store, _note_transform_provider(installation.chat_provider, chat_health)
        ),
        promote=PromoteNoteToSource(note_store, source_acquisition),
        display_names=lambda ids: display_names(engine, ids),
    )
    completion_provider = _completion_provider(installation.chat_provider, chat_health)
    app = build_app(
        users=users,
        hasher=Argon2PasswordHasher(),
        sessions=PgSessionTokenStore(engine, secret_key=settings.secret_key, clock=clock),
        custody=PgNotebookCustodyStore(engine),
        audit=audit,
        notebooks=notebooks,
        notebook_store=notebook_store,
        settings=settings,
        clock=clock,
        jobs=jobs,
        job_activity_provider=lambda: job_activity(engine, clock.now()),
        retrieval=retrieval,
        index_config=index_config,
        grounding=grounding,
        conversations=conversations,
        completion=completion_provider,
        research=ResearchRunDeps(
            store=research_store,
            create=CreateResearchRun(research_store),
            start=StartResearchRun(research_store, jobs),
            pause=PauseResearchRun(research_store),
            resume=ResumeResearchRun(research_store, jobs),
            cancel=CancelResearchRun(research_store, jobs),
        ),
        artifacts=artifacts,
        notes=notes,
        seed_onboarding=SeedFeatureGuide(notebook_store, CreateNote(note_store)),
        health=DeploymentHealth(
            engine,
            installation.blob_root,
            installation.prerequisites_file,
            required_postgres_major=installation.required_postgres_major,
        ),
        capability_runtime=CapabilityRuntime(
            enabled_feature_flags=frozenset(
                FeatureFlag(flag) for flag in installation.enabled_capability_flags
            ),
            configured_providers=_configured_provider_ids(installation),
        ),
        source_acquisition=source_acquisition,
        source_catalog=source_catalog,
        web_source_acquisition=web_source_acquisition,
        public_video_acquisition=public_video_acquisition,
        source_purge=PgSourcePurge(
            engine,
            NoOpBackupExpiryScheduler(),
            blob_store,
        ),
        server_components=ServerComponents(
            worker=lambda: probe_worker(engine, clock.now()),
            chat_provider=(
                _fake_chat_probe
                if installation.chat_provider is ChatProvider.FAKE
                else _provider_probe(chat_health)
            ),
            embedding_provider=(
                None if embedding_client is None else _provider_probe(embedding_health)
            ),
        ),
    )
    app.router.add_event_handler("shutdown", fetch_service.aclose)
    return app


def _provider_probe(health: ProviderHealth) -> Callable[[], ProbeOutcome]:
    """Map a provider's last-call evidence onto the health-surface outcome."""

    def probe() -> ProbeOutcome:
        snapshot = health.snapshot()
        state = ServerComponentStatus.OK if snapshot.healthy else ServerComponentStatus.DEGRADED
        return ProbeOutcome(state, snapshot.detail)

    return probe


def _fake_chat_probe() -> ProbeOutcome:
    """Report the deterministic fake provider as healthy by construction (no probing)."""
    return ProbeOutcome(ServerComponentStatus.OK, "deterministic fake provider")
