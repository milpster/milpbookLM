"""Source status, selection, rename, and explicitly deferred purge routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from milpbooklm_application.audit_actions import AuditAction
from milpbooklm_application.job_actor import InitiatingActor
from milpbooklm_application.source_acquisition import (
    SourceCatalog,
    SourceConflictError,
    SourceNotFoundError,
)
from milpbooklm_application.source_lifecycle import SourcePurge
from milpbooklm_application.web_fetch import AcquireWebSource, AcquireWebSourceCommand
from milpbooklm_domain.acquisition import AcquisitionError
from milpbooklm_domain.jobs import CapacityClass
from milpbooklm_domain.policy import PolicyAction
from starlette import status

from .deps import ApiDeps, PrincipalDependency
from .security import Principal
from .source_guide_routes import build_source_guide_router
from .source_http import RenameSourceRequest, authorize_notebook, problem, source_payload


def build_source_lifecycle_router(
    deps: ApiDeps,
    principal_dependency: PrincipalDependency,
    catalog: SourceCatalog,
    purge: SourcePurge | None = None,
    acquire_web: AcquireWebSource | None = None,
) -> APIRouter:
    """Compose source metadata routes before selection and purge routes."""
    router = APIRouter()
    router.include_router(build_source_guide_router(deps, principal_dependency, catalog))
    router.include_router(_build_metadata_router(deps, principal_dependency, catalog))
    router.include_router(_build_selection_router(deps, principal_dependency, catalog))
    router.include_router(_build_refresh_router(deps, principal_dependency, catalog, acquire_web))
    router.include_router(_build_purge_preview_router(deps, principal_dependency, catalog, purge))
    router.include_router(_build_purge_confirm_router(deps, principal_dependency, catalog, purge))
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

    return router


def _build_refresh_router(
    deps: ApiDeps,
    principal_dependency: PrincipalDependency,
    catalog: SourceCatalog,
    acquire_web: AcquireWebSource | None,
) -> APIRouter:
    router = APIRouter()

    @router.post("/{source_id}/refresh", response_model=None)
    async def refresh_source(
        source_id: uuid.UUID,
        principal: Principal = Depends(principal_dependency),
    ) -> JSONResponse:
        view = catalog.get(source_id, principal.user.id)
        if view is None:
            return JSONResponse(status_code=404, content={"detail": "source not found"})
        denied = authorize_notebook(deps, principal, view.notebook_id, PolicyAction.SOURCE_MUTATE)
        if denied is not None:
            return denied
        remote_url = catalog.refresh_url(source_id, principal.user.id)
        if acquire_web is None or remote_url is None:
            return problem(
                "refresh_unsupported",
                "source is not a refreshable remote snapshot",
                status.HTTP_409_CONFLICT,
            )
        try:
            refreshed, created, job_id = await acquire_web(
                AcquireWebSourceCommand(
                    notebook_id=view.notebook_id,
                    actor_id=principal.user.id,
                    title=view.display_title,
                    url=remote_url,
                    refresh_source_id=source_id,
                )
            )
        except AcquisitionError as exc:
            return problem(exc.code.value, exc.detail, status.HTTP_422_UNPROCESSABLE_CONTENT)
        payload = source_payload(refreshed, job_id)
        payload["created"] = created
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=payload)

    return router


def _build_purge_preview_router(
    deps: ApiDeps,
    principal_dependency: PrincipalDependency,
    catalog: SourceCatalog,
    purge: SourcePurge | None,
) -> APIRouter:
    router = APIRouter()

    @router.post("/{source_id}/purge-preview", response_model=None)
    async def purge_preview(
        source_id: uuid.UUID,
        principal: Principal = Depends(principal_dependency),
    ) -> JSONResponse:
        view = catalog.get(source_id, principal.user.id)
        if view is None:
            return JSONResponse(status_code=404, content={"detail": "source not found"})
        denied = authorize_notebook(deps, principal, view.notebook_id, PolicyAction.SOURCE_MUTATE)
        if denied is not None:
            return denied
        if purge is None:
            return problem(
                "purge_unavailable",
                "purge service unavailable",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        preview = purge.preview(source_id, principal.user.id)
        if preview is None:
            return JSONResponse(status_code=404, content={"detail": "source not found"})
        return JSONResponse(content={"source_id": str(source_id), "counts": dict(preview.counts)})

    return router


def _build_purge_confirm_router(
    deps: ApiDeps,
    principal_dependency: PrincipalDependency,
    catalog: SourceCatalog,
    purge: SourcePurge | None,
) -> APIRouter:
    router = APIRouter()

    @router.post("/{source_id}/purge-confirm", response_model=None)
    async def purge_confirm(
        source_id: uuid.UUID,
        principal: Principal = Depends(principal_dependency),
    ) -> JSONResponse:
        view = catalog.get(source_id, principal.user.id)
        if view is None:
            return JSONResponse(status_code=404, content={"detail": "source not found"})
        denied = authorize_notebook(deps, principal, view.notebook_id, PolicyAction.SOURCE_MUTATE)
        if denied is not None:
            return denied
        if purge is None or deps.jobs is None:
            return problem(
                "purge_unavailable",
                "purge service unavailable",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        mark = purge.mark(source_id, principal.user.id)
        if mark is None:
            return JSONResponse(status_code=404, content={"detail": "source not found"})
        job, _ = deps.jobs.enqueue(
            kind="source.purge_erase",
            payload={"purge_task_id": str(mark.task_id)},
            actor=InitiatingActor(user_id=principal.user.id),
            capacity_class=CapacityClass.INGESTION_INDEXING,
            notebook_id=view.notebook_id,
            capability="source_mutate",
            idempotency_key=f"purge:{mark.task_id}",
        )
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "source_id": str(source_id),
                "purge_task_id": str(mark.task_id),
                "job_id": str(job.id),
                "state": "marked",
                "counts": dict(mark.counts),
            },
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
    denied = authorize_notebook(deps, principal, current.notebook_id, PolicyAction.SOURCE_MUTATE)
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
