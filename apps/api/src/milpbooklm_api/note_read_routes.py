"""Authorization-filtered note and revision reads."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from milpbooklm_domain.policy import PolicyAction
from starlette import status

from .deps import ApiDeps, NoteDeps, PrincipalDependency
from .note_http import note_payload, revision_payload
from .security import Principal
from .source_http import authorize_notebook, problem


def _build_notebook_note_router(
    deps: ApiDeps, principal_dependency: PrincipalDependency, note_deps: NoteDeps
) -> APIRouter:
    router = APIRouter()

    @router.get("/notebooks/{notebook_id}/notes", response_model=None)
    def list_notes(
        notebook_id: uuid.UUID,
        principal: Principal = Depends(principal_dependency),
    ) -> JSONResponse:
        denied = authorize_notebook(
            deps, principal, notebook_id, PolicyAction.READ_CONTENT
        )
        if denied is not None:
            return denied
        return JSONResponse(
            content={
                "notes": [note_payload(note) for note in note_deps.store.list_notes(notebook_id)]
            }
        )

    return router


def _build_logical_note_router(
    deps: ApiDeps, principal_dependency: PrincipalDependency, note_deps: NoteDeps
) -> APIRouter:
    router = APIRouter()

    @router.get("/notes/{note_id}", response_model=None)
    def get_note(
        note_id: uuid.UUID,
        principal: Principal = Depends(principal_dependency),
    ) -> JSONResponse:
        note = note_deps.store.get_note(note_id)
        if note is None:
            return problem(
                "note_not_found", "note not found", status.HTTP_404_NOT_FOUND
            )
        denied = authorize_notebook(
            deps, principal, note.notebook_id, PolicyAction.READ_CONTENT
        )
        if denied is not None:
            return denied
        return JSONResponse(content=note_payload(note))

    @router.get("/notes/{note_id}/revisions", response_model=None)
    def list_revisions(
        note_id: uuid.UUID,
        principal: Principal = Depends(principal_dependency),
    ) -> JSONResponse:
        note = note_deps.store.get_note(note_id)
        if note is None:
            return problem(
                "note_not_found", "note not found", status.HTTP_404_NOT_FOUND
            )
        denied = authorize_notebook(
            deps, principal, note.notebook_id, PolicyAction.READ_CONTENT
        )
        if denied is not None:
            return denied
        return JSONResponse(
            content={
                "revisions": [
                    revision_payload(revision)
                    for revision in note_deps.store.list_revisions(note_id)
                ]
            }
        )

    return router


def _build_revision_router(
    deps: ApiDeps, principal_dependency: PrincipalDependency, note_deps: NoteDeps
) -> APIRouter:
    router = APIRouter()

    @router.get("/note-revisions/{revision_id}", response_model=None)
    def get_revision(
        revision_id: uuid.UUID,
        principal: Principal = Depends(principal_dependency),
    ) -> JSONResponse:
        revision = note_deps.store.get_revision(revision_id)
        if revision is None:
            return problem(
                "note_revision_not_found",
                "note revision not found",
                status.HTTP_404_NOT_FOUND,
            )
        note = note_deps.store.get_note(revision.note_id)
        if note is None:
            return problem(
                "note_not_found", "note not found", status.HTTP_404_NOT_FOUND
            )
        denied = authorize_notebook(
            deps, principal, note.notebook_id, PolicyAction.READ_CONTENT
        )
        if denied is not None:
            return denied
        return JSONResponse(content=revision_payload(revision))

    return router


def build_note_read_router(
    deps: ApiDeps, principal_dependency: PrincipalDependency, note_deps: NoteDeps
) -> APIRouter:
    """Compose notebook, logical-note, and exact-revision read routes."""
    router = APIRouter()
    router.include_router(_build_notebook_note_router(deps, principal_dependency, note_deps))
    router.include_router(_build_logical_note_router(deps, principal_dependency, note_deps))
    router.include_router(_build_revision_router(deps, principal_dependency, note_deps))
    return router
