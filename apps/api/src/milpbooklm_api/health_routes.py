"""Deployment health and administrator diagnostics routes (ARCH-04-001..022)."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from milpbooklm_adapters.db.harness import current_script_head
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy.exc import SQLAlchemyError
from starlette import status

from .deps import PrincipalDependency
from .security import Principal

# Derived from the migrations script directory (alembic head detection), never
# a hardcoded revision: the constant follows the migrations package in every
# build, so the schema probe cannot go stale when new revisions land.
EXPECTED_SCHEMA_REVISION = current_script_head()
# Production default; dev deployments on an older major override it through
# MILPBOOKLM_REQUIRED_POSTGRES_MAJOR (see InstallationConfig).
REQUIRED_POSTGRES_MAJOR = 18
# Worker liveness is derived from durable job rows (there is no heartbeat
# table): a queued job that has waited longer than the backlog grace has not
# been claimed, and job rows updated inside the activity window prove a live
# claim/transition cycle. Absent both, liveness is honestly unknown.
WORKER_BACKLOG_GRACE = timedelta(minutes=2)
WORKER_ACTIVITY_WINDOW = timedelta(minutes=10)
_SECONDS_PER_MINUTE = 60
_SECONDS_PER_HOUR = 3600


class ComponentState(StrEnum):
    """Bounded component states exposed by health responses."""

    READY = "ready"
    DEGRADED = "degraded"


class ComponentHealth(BaseModel):
    """A secret-free deployment component result."""

    model_config = ConfigDict(frozen=True)

    component: str
    state: ComponentState
    reason: str | None = None


class HealthResponse(BaseModel):
    """Machine-readable aggregate health response."""

    model_config = ConfigDict(frozen=True)

    status: ComponentState
    components: tuple[ComponentHealth, ...] = ()


class DiagnosticsResponse(BaseModel):
    """Installation-admin diagnostics with bounded degradation reasons."""

    model_config = ConfigDict(frozen=True)

    status: ComponentState
    degradations: tuple[ComponentHealth, ...]


class ServerComponentStatus(StrEnum):
    """Bounded statuses for the authenticated component-health surface."""

    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"


class ServerComponent(BaseModel):
    """One server component with its status and a short human-readable label."""

    model_config = ConfigDict(frozen=True)

    component: str
    status: ServerComponentStatus
    detail: str


class ServerComponentsResponse(BaseModel):
    """The per-component server health snapshot (latest owned evidence, never probed ad hoc)."""

    model_config = ConfigDict(frozen=True)

    components: tuple[ServerComponent, ...]


@dataclass(frozen=True, slots=True)
class ProbeOutcome:
    """A single component probe result feeding the server-health surface."""

    status: ServerComponentStatus
    detail: str


@dataclass(frozen=True, slots=True)
class ServerComponents:
    """Injected per-component probes (composition wires the real ones, tests the fakes)."""

    worker: Callable[[], ProbeOutcome]
    chat_provider: Callable[[], ProbeOutcome]
    # None = no embedding endpoint configured on this installation (row omitted).
    embedding_provider: Callable[[], ProbeOutcome] | None = None


def probe_worker(engine: sa.engine.Engine, now: datetime) -> ProbeOutcome:
    """Derive worker liveness from durable job rows; unknown is degraded, never ok."""
    backlog_cutoff = now - WORKER_BACKLOG_GRACE
    try:
        with engine.connect() as connection:
            backlog = int(
                connection.execute(
                    sa.text(
                        "SELECT count(*) FROM jobs "
                        "WHERE status = 'queued' AND enqueued_at < :cutoff"
                    ),
                    {"cutoff": backlog_cutoff},
                ).scalar_one()
            )
            last_activity = connection.execute(
                sa.text("SELECT max(updated_at) FROM jobs")
            ).scalar_one()
    except SQLAlchemyError:
        return ProbeOutcome(
            ServerComponentStatus.DEGRADED, "liveness unknown (jobs table unreadable)"
        )
    if last_activity is not None and last_activity.tzinfo is None:
        last_activity = last_activity.replace(tzinfo=UTC)
    if backlog > 0:
        return ProbeOutcome(
            ServerComponentStatus.DEGRADED, f"{backlog} queued job(s) unclaimed"
        )
    if last_activity is None:
        return ProbeOutcome(ServerComponentStatus.DEGRADED, "no recent worker activity")
    age = now - last_activity
    if age <= WORKER_ACTIVITY_WINDOW:
        return ProbeOutcome(ServerComponentStatus.OK, f"last activity {_age_label(age)}")
    return ProbeOutcome(ServerComponentStatus.DEGRADED, "no recent worker activity")


def _age_label(age: timedelta) -> str:
    seconds = age.total_seconds()
    if seconds < _SECONDS_PER_MINUTE:
        return "just now"
    if seconds < _SECONDS_PER_HOUR:
        return f"{int(seconds // _SECONDS_PER_MINUTE)}m ago"
    return f"{int(seconds // _SECONDS_PER_HOUR)}h ago"


class PrerequisiteReport(BaseModel):
    """Installer output consumed by API readiness."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    ready: bool
    execution_enabled: bool


class DeploymentHealth:
    """Probe deployment dependencies without disclosing configuration values."""

    def __init__(
        self,
        engine: sa.engine.Engine,
        blob_root: Path,
        prerequisites_file: Path,
        required_postgres_major: int = REQUIRED_POSTGRES_MAJOR,
    ) -> None:
        """Bind the database, blob root, installer report and PG major floor."""
        self._engine = engine
        self._blob_root = blob_root
        self._prerequisites_file = prerequisites_file
        self._required_postgres_major = required_postgres_major

    def probe(self) -> tuple[ComponentHealth, ...]:
        """Return current database, schema, blob, and prerequisite states."""
        database, schema = self._probe_database()
        return database, schema, self._probe_blob_root(), self._probe_prerequisites()

    def _probe_database(self) -> tuple[ComponentHealth, ComponentHealth]:
        try:
            with self._engine.connect() as connection:
                connection.execute(sa.text("SELECT 1"))
                version_num = int(
                    connection.execute(
                        sa.text("SELECT current_setting('server_version_num')")
                    ).scalar_one()
                )
                revision = connection.execute(
                    sa.text("SELECT version_num FROM alembic_version LIMIT 1")
                ).scalar_one_or_none()
                vector_ready = bool(
                    connection.execute(
                        sa.text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='vector')")
                    ).scalar_one()
                )
                uuidv7_ready = bool(
                    connection.execute(
                        sa.text("SELECT EXISTS (SELECT 1 FROM pg_proc WHERE proname='uuidv7')")
                    ).scalar_one()
                )
        except (SQLAlchemyError, OSError, TypeError, ValueError):
            unavailable = ComponentHealth(
                component="database",
                state=ComponentState.DEGRADED,
                reason="database_unavailable",
            )
            schema_unknown = ComponentHealth(
                component="schema",
                state=ComponentState.DEGRADED,
                reason="schema_unavailable",
            )
            return unavailable, schema_unknown

        postgres_major = version_num // 10000
        database_ready = (
            postgres_major == self._required_postgres_major and vector_ready and uuidv7_ready
        )
        database_reason = None
        if not database_ready:
            database_reason = "database_runtime_incompatible"
        schema_ready = revision == EXPECTED_SCHEMA_REVISION
        schema_reason = None if schema_ready else "schema_revision_incompatible"
        return (
            ComponentHealth(
                component="database",
                state=(ComponentState.READY if database_ready else ComponentState.DEGRADED),
                reason=database_reason,
            ),
            ComponentHealth(
                component="schema",
                state=(ComponentState.READY if schema_ready else ComponentState.DEGRADED),
                reason=schema_reason,
            ),
        )

    def _probe_blob_root(self) -> ComponentHealth:
        ready = (
            self._blob_root.is_dir()
            and os.access(self._blob_root, os.R_OK)
            and os.access(self._blob_root, os.W_OK)
        )
        return ComponentHealth(
            component="blob",
            state=ComponentState.READY if ready else ComponentState.DEGRADED,
            reason=None if ready else "blob_root_unavailable",
        )

    def _probe_prerequisites(self) -> ComponentHealth:
        try:
            report = PrerequisiteReport.model_validate_json(
                self._prerequisites_file.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError):
            return ComponentHealth(
                component="execution_prerequisites",
                state=ComponentState.DEGRADED,
                reason="prerequisite_report_unavailable",
            )
        ready = report.ready and report.execution_enabled
        return ComponentHealth(
            component="execution_prerequisites",
            state=ComponentState.READY if ready else ComponentState.DEGRADED,
            reason=None if ready else "execution_prerequisites_unsatisfied",
        )


def build_health_router(
    health: DeploymentHealth | None,
    principal: PrincipalDependency,
    server_components: ServerComponents | None = None,
) -> APIRouter:
    """Build public health probes and protected installation diagnostics."""
    router = APIRouter()

    @router.get("/health/live", response_model=HealthResponse)
    async def live() -> HealthResponse:
        return HealthResponse(status=ComponentState.READY)

    @router.get("/health/ready", response_model=HealthResponse)
    async def ready() -> JSONResponse:
        components = _components(health)
        aggregate = _aggregate(components)
        return JSONResponse(
            status_code=(
                status.HTTP_200_OK
                if aggregate is ComponentState.READY
                else status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            content=HealthResponse(status=aggregate, components=components).model_dump(mode="json"),
        )

    @router.get("/api/v1/health/components", response_model=ServerComponentsResponse)
    async def components(
        authenticated: Principal = Depends(principal),
    ) -> ServerComponentsResponse:
        """Return the per-component server health snapshot (authenticated, count/label only)."""
        del authenticated
        return ServerComponentsResponse(
            components=_server_components(health, server_components)
        )

    @router.get("/api/v1/admin/diagnostics", response_model=DiagnosticsResponse)
    async def diagnostics(
        authenticated: Principal = Depends(principal),
    ) -> JSONResponse:
        if not authenticated.user.installation_admin:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "installation administrator required"},
            )
        components = _components(health)
        degradations = tuple(
            component for component in components if component.state is ComponentState.DEGRADED
        )
        aggregate = _aggregate(components)
        return JSONResponse(
            content=DiagnosticsResponse(
                status=aggregate,
                degradations=degradations,
            ).model_dump(mode="json")
        )

    return router


_DATABASE_DETAIL = {
    "database_unavailable": "database unreachable",
    "database_runtime_incompatible": "database runtime incompatible",
    "schema_revision_incompatible": "schema revision mismatch",
    "schema_unavailable": "schema state unknown",
}


def _server_components(
    health: DeploymentHealth | None, parts: ServerComponents | None
) -> tuple[ServerComponent, ...]:
    probed: Mapping[str, ComponentHealth] = (
        {component.component: component for component in health.probe()}
        if health is not None
        else {}
    )
    database = _database_component(probed)
    blob = _blob_component(probed)
    worker = _probe_component("worker", parts.worker() if parts is not None else None)
    chat = _probe_component("chat_provider", parts.chat_provider() if parts is not None else None)
    embedding = (
        _probe_component("embedding_provider", parts.embedding_provider())
        if parts is not None and parts.embedding_provider is not None
        else None
    )
    search = _search_component(database, embedding)
    rows = [database, blob, worker, chat]
    if embedding is not None:
        rows.append(embedding)
    rows.append(search)
    return tuple(rows)


def _database_component(probed: Mapping[str, ComponentHealth]) -> ServerComponent:
    if not probed:
        return ServerComponent(
            component="database",
            status=ServerComponentStatus.DOWN,
            detail="health probes not wired",
        )
    for name in ("database", "schema"):
        component = probed.get(name)
        if component is not None and component.state is ComponentState.DEGRADED:
            reason = component.reason or ""
            detail = _DATABASE_DETAIL.get(reason, f"{name} state unknown")
            state = (
                ServerComponentStatus.DOWN
                if reason == "database_unavailable"
                else ServerComponentStatus.DEGRADED
            )
            return ServerComponent(component="database", status=state, detail=detail)
    return ServerComponent(
            component="database", status=ServerComponentStatus.OK, detail="connected"
        )


def _blob_component(probed: Mapping[str, ComponentHealth]) -> ServerComponent:
    if not probed:
        return ServerComponent(
            component="blob_store",
            status=ServerComponentStatus.DOWN,
            detail="health probes not wired",
        )
    blob = probed.get("blob")
    if blob is not None and blob.state is ComponentState.DEGRADED:
        return ServerComponent(
            component="blob_store",
            status=ServerComponentStatus.DOWN,
            detail="blob root unavailable",
        )
    return ServerComponent(
            component="blob_store", status=ServerComponentStatus.OK, detail="blob root writable"
        )


def _probe_component(name: str, outcome: ProbeOutcome | None) -> ServerComponent:
    if outcome is None:
        return ServerComponent(
            component=name, status=ServerComponentStatus.DEGRADED, detail="not wired"
        )
    return ServerComponent(component=name, status=outcome.status, detail=outcome.detail)


def _search_component(
    database: ServerComponent, embedding: ServerComponent | None
) -> ServerComponent:
    if database.status is not ServerComponentStatus.OK:
        return ServerComponent(
            component="search",
            status=ServerComponentStatus.DEGRADED,
            detail="unavailable (database down)",
        )
    if embedding is None:
        return ServerComponent(
            component="search", status=ServerComponentStatus.OK, detail="lexical search"
        )
    if embedding.status is not ServerComponentStatus.OK:
        return ServerComponent(
            component="search",
            status=ServerComponentStatus.DEGRADED,
            detail="vector search degraded, lexical fallback",
        )
    return ServerComponent(
        component="search",
        status=ServerComponentStatus.OK,
        detail="hybrid search (lexical + vector)",
    )


def _components(health: DeploymentHealth | None) -> tuple[ComponentHealth, ...]:
    if health is not None:
        return health.probe()
    return (
        ComponentHealth(
            component="deployment",
            state=ComponentState.DEGRADED,
            reason="deployment_health_not_configured",
        ),
    )


def _aggregate(components: tuple[ComponentHealth, ...]) -> ComponentState:
    if all(component.state is ComponentState.READY for component in components):
        return ComponentState.READY
    return ComponentState.DEGRADED
