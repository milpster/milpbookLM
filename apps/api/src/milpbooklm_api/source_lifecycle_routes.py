"""Source status, selection, rename, and explicitly deferred purge routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from milpbooklm_application.audit_actions import AuditAction
from milpbooklm_application.source_acquisition import (
    SourceCatalog,
    SourceConflictError,
    SourceNotFoundError,
)
from milpbooklm_domain.policy import PolicyAction
from starlette import status

from .deps import ApiDeps, PrincipalDependency
from .security import Principal
from .source_http import RenameSourceRequest, authorize_notebook, problem, source_payload


def build_source_lifecycle_router(
    deps: ApiDeps,
    principal_dependency: PrincipalDependency,
    catalog: SourceCatalog,
) -> APIRouter:
    """Compose source metadata routes before selection and purge routes."""
    router = APIRouter()
    router.include_router(_build_metadata_router(deps, principal_dependency, catalog))
    router.include_router(_build_selection_router(deps, principal_dependency, catalog))
    return router


def _build_metadata_router(
    deps: ApiDeps,
    principal_dependency: PrincipalDependency,
    catalog: SourceCatalog,
) -> APIRouter:
    router = APIRouter()

    @router.get("/{source_id}", response_model=None)
    async def source_status(
        source_id: uuid.UUID,
        principal: Principal = Depends(principal_dependency),
    ) -> JSONResponse:
        view = catalog.get(source_id, principal.user.id)
        if view is None:
            return JSONResponse(status_code=404, content={"detail": "source not found"})
        denied = authorize_notebook(deps, principal, view.notebook_id, PolicyAction.READ_CONTENT)
        if denied is not None:
            return denied
        return JSONResponse(content=source_payload(view))

    @router.patch("/{source_id}", response_model=None)
    async def rename_source(
        source_id: uuid.UUID,
        body: RenameSourceRequest,
        if_match: str = Header(alias="If-Match"),
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
            updated = catalog.rename(source_id, principal.user.id, body.title, if_match)
        except SourceConflictError:
            return problem(
                "etag_conflict",
                "source metadata changed",
                status.HTTP_412_PRECONDITION_FAILED,
            )
        deps.audit.record(
            actor_id=principal.user.id,
            action=AuditAction.SOURCE_RENAMED.value,
            subject_kind="source",
            subject_id=source_id,
        )
        return JSONResponse(content=source_payload(updated))

    return router


def _build_selection_router(
    deps: ApiDeps,
    principal_dependency: PrincipalDependency,
    catalog: SourceCatalog,
) -> APIRouter:
    router = APIRouter()

    @router.post("/{source_id}/select", response_model=None)
    async def select_source(
        source_id: uuid.UUID,
        principal: Principal = Depends(principal_dependency),
    ) -> JSONResponse:
        return _set_selected(deps, principal, catalog, source_id, selected=True)

    @router.post("/{source_id}/remove", response_model=None)
    async def remove_source(
        source_id: uuid.UUID,
        principal: Principal = Depends(principal_dependency),
    ) -> JSONResponse:
        return _set_selected(deps, principal, catalog, source_id, selected=False)

    @router.post("/{source_id}/purge-preview", response_model=None)
    @router.post("/{source_id}/purge-confirm", response_model=None)
    async def purge_deferred(
        source_id: uuid.UUID,
        principal: Principal = Depends(principal_dependency),
    ) -> JSONResponse:
        view = catalog.get(source_id, principal.user.id)
        if view is None:
            return JSONResponse(status_code=404, content={"detail": "source not found"})
        denied = authorize_notebook(
            deps, principal, view.notebook_id, PolicyAction.SOURCE_MUTATE
        )
        if denied is not None:
            return denied
        return problem(
            "not_implemented_until_ing_02d",
            "purge preview and confirmation are implemented by task 24",
            status.HTTP_501_NOT_IMPLEMENTED,
        )

    return router


def _set_selected(
    deps: ApiDeps,
    principal: Principal,
    catalog: SourceCatalog,
    source_id: uuid.UUID,
    *,
    selected: bool,
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
        updated = catalog.set_selected(source_id, principal.user.id, selected=selected)
    except SourceNotFoundError:
        return JSONResponse(status_code=404, content={"detail": "source not found"})
    deps.audit.record(
        actor_id=principal.user.id,
        action=(AuditAction.SOURCE_SELECTED if selected else AuditAction.SOURCE_REMOVED).value,
        subject_kind="source",
        subject_id=source_id,
    )
    return JSONResponse(content=source_payload(updated))
