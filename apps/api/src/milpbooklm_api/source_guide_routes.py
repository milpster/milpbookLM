"""Activation and deterministic phase-one Source Guide routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from milpbooklm_application.audit_actions import AuditAction
from milpbooklm_application.source_acquisition import SourceCatalog, SourceNotFoundError
from milpbooklm_domain.policy import PolicyAction
from starlette import status

from .deps import ApiDeps, PrincipalDependency
from .security import Principal
from .source_http import authorize_notebook, problem, source_payload


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
        return JSONResponse(status_code=status.HTTP_200_OK, content=source_payload(view))

    return router
