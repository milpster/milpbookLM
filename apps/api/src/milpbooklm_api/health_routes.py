"""Deployment health and administrator diagnostics routes (ARCH-04-001..022)."""

from __future__ import annotations

import os
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
