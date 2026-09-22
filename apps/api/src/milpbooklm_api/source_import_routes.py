"""Streaming multipart and paste-text source acquisition routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from milpbooklm_application.audit_actions import AuditAction
from milpbooklm_application.source_acquisition import AcquireSource, AcquireSourceCommand
from milpbooklm_application.web_fetch import AcquireWebSource, AcquireWebSourceCommand
from milpbooklm_domain.acquisition import AcquisitionError
from milpbooklm_domain.policy import PolicyAction
from starlette import status

from .deps import ApiDeps, PrincipalDependency
from .multipart_stream import MultipartError, multipart_file_chunks
from .security import Principal
from .source_http import (
    PasteTextRequest,
    WebUrlRequest,
    authorize_notebook,
    problem,
    single_chunk,
    source_payload,
)


def build_source_import_router(
    deps: ApiDeps,
    principal_dependency: PrincipalDependency,
    acquire: AcquireSource,
    acquire_web: AcquireWebSource | None = None,
) -> APIRouter:
    """Build streaming upload and paste acquisition routes."""
    router = APIRouter()

    @router.post("/import", response_model=None)
    async def import_source(
        request: Request,
        notebook_id: uuid.UUID,
        principal: Principal = Depends(principal_dependency),
    ) -> JSONResponse:
        denied = authorize_notebook(deps, principal, notebook_id, PolicyAction.SOURCE_MUTATE)
        if denied is not None:
            return denied
        try:
            view, created, job_id = await acquire(
                AcquireSourceCommand(
                    notebook_id=notebook_id,
                    actor_id=principal.user.id,
                    display_title="Uploaded source",
                    origin_kind="upload",
                ),
                multipart_file_chunks(request.stream(), request.headers.get("content-type", "")),
            )
        except MultipartError as exc:
            deps.audit.record(
                actor_id=principal.user.id,
                action=AuditAction.ACQUISITION_REJECTED.value,
                subject_kind="notebook",
                subject_id=notebook_id,
                details={"error_code": "corrupt"},
            )
            return problem("corrupt", str(exc), status.HTTP_422_UNPROCESSABLE_CONTENT)
        except AcquisitionError as exc:
            return problem(exc.code.value, exc.detail, status.HTTP_422_UNPROCESSABLE_CONTENT)
        return JSONResponse(
            status_code=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
            content=source_payload(view, job_id),
        )

    @router.post("/paste", response_model=None)
    async def paste_source(
        body: PasteTextRequest,
        principal: Principal = Depends(principal_dependency),
    ) -> JSONResponse:
        denied = authorize_notebook(
            deps, principal, body.notebook_id, PolicyAction.SOURCE_MUTATE
        )
        if denied is not None:
            return denied
        try:
            view, created, job_id = await acquire(
                AcquireSourceCommand(
                    notebook_id=body.notebook_id,
                    actor_id=principal.user.id,
                    display_title=body.title,
                    origin_kind="paste",
                ),
                single_chunk(body.text.encode("utf-8")),
            )
        except AcquisitionError as exc:
            return problem(exc.code.value, exc.detail, status.HTTP_422_UNPROCESSABLE_CONTENT)
        return JSONResponse(
            status_code=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
            content=source_payload(view, job_id),
        )

    if acquire_web is not None:
        router.include_router(_build_web_url_router(deps, principal_dependency, acquire_web))

    return router


def _build_web_url_router(
    deps: ApiDeps,
    principal_dependency: PrincipalDependency,
    acquire_web: AcquireWebSource,
) -> APIRouter:
    router = APIRouter()

    @router.post("/web-url", response_model=None)
    async def acquire_web_url(
        body: WebUrlRequest,
        principal: Principal = Depends(principal_dependency),
    ) -> JSONResponse:
        denied = authorize_notebook(
            deps, principal, body.notebook_id, PolicyAction.SOURCE_MUTATE
        )
        if denied is not None:
            return denied
        try:
            view, created, job_id = await acquire_web(
                AcquireWebSourceCommand(
                    notebook_id=body.notebook_id,
                    actor_id=principal.user.id,
                    title=body.title,
                    url=body.url,
                )
            )
        except AcquisitionError as exc:
            return problem(exc.code.value, exc.detail, status.HTTP_422_UNPROCESSABLE_CONTENT)
        return JSONResponse(
            status_code=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
            content=source_payload(view, job_id),
        )

    return router
