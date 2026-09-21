"""Activation and deterministic phase-one Source Guide routes."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from milpbooklm_application.audit_actions import AuditAction
from milpbooklm_application.indexing import (
    config_to_payload,
    generation_id_for,
    idempotency_key_for,
)
from milpbooklm_application.job_actor import InitiatingActor
from milpbooklm_application.source_acquisition import (
    SourceCatalog,
    SourceNotFoundError,
    SourceView,
)
from milpbooklm_domain.jobs import CapacityClass
from milpbooklm_domain.policy import PolicyAction
from milpbooklm_domain.telemetry import current_context
from starlette import status

from .deps import ApiDeps, PrincipalDependency
from .security import Principal
from .source_http import authorize_notebook, problem, source_payload

logger = logging.getLogger(__name__)


def build_source_guide_router(
    deps: ApiDeps,
    principal_dependency: PrincipalDependency,
    catalog: SourceCatalog,
) -> APIRouter:
    """Expose direct activation after worker parsing and metadata-only guides."""
    router = APIRouter()
    router.include_router(_build_guide_router(deps, principal_dependency, catalog))
    router.include_router(_build_activation_router(deps, principal_dependency, catalog))
    return router


def _build_guide_router(
    deps: ApiDeps,
    principal_dependency: PrincipalDependency,
    catalog: SourceCatalog,
) -> APIRouter:
    """Metadata-only guide for an active canonical source."""
    router = APIRouter()

    @router.get("/{source_id}/guide", response_model=None)
    async def source_guide(
        source_id: uuid.UUID,
        principal: Principal = Depends(principal_dependency),
    ) -> JSONResponse:
        view = catalog.get(source_id, principal.user.id)
        if view is None:
            return JSONResponse(status_code=404, content={"detail": "source not found"})
        denied = authorize_notebook(
            deps, principal, view.notebook_id, PolicyAction.READ_CONTENT
        )
        if denied is not None:
            return denied
        guide = catalog.guide(source_id, principal.user.id)
        if guide is None:
            return problem(
                "source_guide_unavailable",
                "a Source Guide requires an active canonical source version",
                status.HTTP_409_CONFLICT,
            )
        return JSONResponse(
            content={
                "source_id": str(guide.source_id),
                "source_version_id": str(guide.source_version_id),
                "summary": guide.summary,
                "labels": list(guide.labels),
                "restrictions": list(guide.restrictions),
            }
        )

    return router


def _build_activation_router(
    deps: ApiDeps,
    principal_dependency: PrincipalDependency,
    catalog: SourceCatalog,
) -> APIRouter:
    """Direct transactional activation of an already-parsed source version."""
    router = APIRouter()

    @router.post("/{source_id}/activate", response_model=None)
    async def activate_source(
        source_id: uuid.UUID,
        principal: Principal = Depends(principal_dependency),
    ) -> JSONResponse:
        current = catalog.get(source_id, principal.user.id)
        if current is None:
            return JSONResponse(status_code=404, content={"detail": "source not found"})
        denied = authorize_notebook(
            deps, principal, current.notebook_id, PolicyAction.SOURCE_MUTATE
        )
        if denied is not None:
            return denied
        try:
            activated = catalog.activate(source_id, principal.user.id)
        except SourceNotFoundError:
            return JSONResponse(status_code=404, content={"detail": "source not found"})
        if not activated:
            return problem(
                "source_activation_conflict",
                "a parsed canonical source version is required for activation",
                status.HTTP_409_CONFLICT,
            )
        deps.audit.record(
            actor_id=principal.user.id,
            action=AuditAction.SOURCE_ACTIVATED.value,
            subject_kind="source",
            subject_id=source_id,
        )
        view = catalog.get(source_id, principal.user.id)
        if view is None:
            return JSONResponse(status_code=404, content={"detail": "source not found"})
        _enqueue_index_job(deps, principal.user.id, view, catalog, source_id)
        return JSONResponse(status_code=status.HTTP_200_OK, content=source_payload(view))

    return router


def _enqueue_index_job(
    deps: ApiDeps,
    actor_id: uuid.UUID,
    view: SourceView,
    catalog: SourceCatalog,
    source_id: uuid.UUID,
) -> None:
    """Enqueue the worker-driven index build (enqueue only; the worker owns the lifecycle)."""
    if deps.jobs is None or deps.index_config is None:
        return
    document_id = catalog.active_document_id(source_id, actor_id)
    if document_id is None:
        return
    config = deps.index_config
    source_version_id = view.source_version_id
    notebook_id = view.notebook_id
    model = config.embedding.model
    dimension = config.embedding.dimension
    profile_revision = config.profile.revision
    context = current_context()
    deps.jobs.enqueue(
        kind="ingestion.index",
        payload={
            "source_id": str(source_id),
            "notebook_id": str(notebook_id),
            "source_version_id": str(source_version_id),
            "canonical_document_id": str(document_id),
            "generation_id": str(
                generation_id_for(source_version_id, model, dimension, profile_revision)
            ),
            **config_to_payload(config),
        },
        actor=InitiatingActor(
            user_id=actor_id,
            request_id=context.request_id if context is not None else None,
            trace_id=context.trace_id if context is not None else None,
        ),
        capacity_class=CapacityClass.INGESTION_INDEXING,
        notebook_id=notebook_id,
        capability="source_mutate",
        idempotency_key=idempotency_key_for(
            source_version_id, model, dimension, profile_revision
        ),
    )
    logger.info(
        "index job enqueued: source=%s source_version=%s", source_id, source_version_id
    )
