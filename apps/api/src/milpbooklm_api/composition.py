"""
Composition root: wire use cases to adapters and build the API app.

``build_app`` is the test/QA seam (explicit ports); ``create_app`` is the
production entry point (typed environment config + PostgreSQL). ``build_create_notebook``
is the earlier skeleton wiring, kept for the existing unit tests.
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from fastapi import FastAPI, HTTPException, Request
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
from milpbooklm_adapters.notebook_repository import InMemoryNotebookRepository
from milpbooklm_adapters.security.argon2 import Argon2PasswordHasher
from milpbooklm_adapters.security.clock import SystemClock
from milpbooklm_adapters.security.custody_store import PgNotebookCustodyStore
from milpbooklm_adapters.security.notebook_reader import PgNotebookReader
from milpbooklm_adapters.security.notebook_store import PgNotebookStore
from milpbooklm_adapters.security.pg_identity import PgAuditLog, PgUserRepository
from milpbooklm_adapters.security.session_store import PgSessionTokenStore
from milpbooklm_adapters.sources import FilesystemQuarantineStore, PgSourceCatalog
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
from milpbooklm_application.retrieval import RetrieveChunks
from milpbooklm_application.source_acquisition import AcquireSource, SourceCatalog
from milpbooklm_application.structured_logging import configure_structured_logging
from milpbooklm_application.web_fetch import AcquireWebSource
from milpbooklm_domain.capabilities import CapabilityDefinition, DependencyId, FeatureFlag
from milpbooklm_domain.indexing import STRUCTURAL_CHUNKER_V1
from starlette import status

from .auth_routes import build_auth_router
from .capability_registry import load_capability_registry
from .capability_routes import build_capability_router
from .config import ChatProvider, InstallationConfig
from .config_loader import load_config
from .conversation_routes import build_conversation_router
from .deps import ApiDeps
from .grounding_routes import build_grounding_router
from .health_routes import DeploymentHealth, build_health_router
from .job_routes import build_job_router
from .notebook_overview_routes import build_notebook_overview_router
from .notebook_routes import build_notebook_router
from .observability import (
    CorrelationMiddleware,
    SecurityHeadersMiddleware,
    UnhandledErrorMiddleware,
)
from .retrieval_routes import build_retrieval_router
from .security import (
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
    provider: ChatProvider,
) -> LlamaCppCompletionProvider | FakeGroundingCompletionProvider:
    match provider:
        case ChatProvider.LLAMA_CPP:
            return LlamaCppCompletionProvider()
        case ChatProvider.FAKE:
            return FakeGroundingCompletionProvider()


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
    retrieval: RetrieveChunks | None = None,
    index_config: IndexBuildConfig | None = None,
    grounding: PgGroundingStore | None = None,
    conversations: PgConversationStore | None = None,
    completion: LlamaCppCompletionProvider | FakeGroundingCompletionProvider | None = None,
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

    definitions = (
        load_capability_registry() if capability_definitions is None else capability_definitions
    )
    runtime = CapabilityRuntime() if capability_runtime is None else capability_runtime
    app.include_router(build_health_router(health, principal))
    app.include_router(build_capability_router(definitions, runtime, health))
    app.include_router(build_auth_router(deps, principal))
    app.include_router(build_notebook_router(deps, principal))
    app.include_router(build_retrieval_router(deps, principal))
    app.include_router(build_grounding_router(deps, principal))
    app.include_router(build_conversation_router(deps, principal))
    app.include_router(build_notebook_overview_router(deps, principal))
    if jobs is not None:
        app.include_router(build_job_router(deps, principal, jobs))
    if source_acquisition is not None and source_catalog is not None:
        app.include_router(
            build_source_router(
                deps,
                principal,
                source_acquisition,
                source_catalog,
                web_source_acquisition,
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
    return config, LlamaCppEmbeddingClient(base_url, model)


def create_app() -> FastAPI:
    """Build the production app from the environment (typed config + PG app DSN)."""
    configure_structured_logging()
    installation = load_config(os.environ).installation
    engine = make_engine(installation.database_url.get_secret_value())
    clock = SystemClock()
    settings = SecuritySettings(
        secret_key=installation.secret_key.get_secret_value(),
        base_url=installation.base_url,
    )
    users = PgUserRepository(engine)
    notebooks = PgNotebookReader(engine)
    audit = PgAuditLog(engine)
    jobs = build_job_ports(engine, users, notebooks)
    source_catalog = PgSourceCatalog(engine)
    source_acquisition = AcquireSource(
        quarantine=FilesystemQuarantineStore(
            installation.blob_root,
            max_bytes=installation.max_acquisition_bytes,
        ),
        blobs=FilesystemBlobStore(
            installation.blob_root,
            PgBlobRepository(engine),
            clock,
        ),
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
    index_config, embedding_client = _embedding_wiring(installation)
    retrieval = RetrieveChunks(
        retrieval=PgRetrievalService(engine),
        embeddings=embedding_client,
        expected_dimension=(index_config.embedding.dimension if index_config is not None else None),
    )
    grounding = PgGroundingStore(engine)
    conversations = PgConversationStore(engine)
    app = build_app(
        users=users,
        hasher=Argon2PasswordHasher(),
        sessions=PgSessionTokenStore(engine, secret_key=settings.secret_key, clock=clock),
        custody=PgNotebookCustodyStore(engine),
        audit=audit,
        notebooks=notebooks,
        notebook_store=PgNotebookStore(engine),
        settings=settings,
        clock=clock,
        jobs=jobs,
        retrieval=retrieval,
        index_config=index_config,
        grounding=grounding,
        conversations=conversations,
        completion=_completion_provider(installation.chat_provider),
        health=DeploymentHealth(
            engine,
            installation.blob_root,
            installation.prerequisites_file,
        ),
        capability_runtime=CapabilityRuntime(
            enabled_feature_flags=frozenset(
                FeatureFlag(flag) for flag in installation.enabled_capability_flags
            ),
            configured_providers=frozenset(
                DependencyId(provider) for provider in installation.configured_provider_capabilities
            ),
        ),
        source_acquisition=source_acquisition,
        source_catalog=source_catalog,
        web_source_acquisition=web_source_acquisition,
    )
    app.router.add_event_handler("shutdown", fetch_service.aclose)
    return app
