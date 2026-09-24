"""Policy-checked note creation, revision, transform, and promotion routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from milpbooklm_application.audit_actions import AuditAction
from milpbooklm_application.note_core import (
    CreateNoteCommand,
    EditNoteCommand,
    NoteConflictError,
    NoteNotEditableError,
    NoteSelectionError,
    NoteSnapshot,
    PromoteNoteCommand,
    SaveResponseToNoteCommand,
    TransformNotesCommand,
)
from milpbooklm_domain.policy import PolicyAction
from milpbooklm_domain.telemetry import current_context
from starlette import status

from .deps import ApiDeps, NoteDeps, PrincipalDependency
from .note_http import (
    CreateNoteRequest,
    EditNoteRequest,
    PromoteNoteRequest,
    SaveResponseRequest,
    TransformNotesRequest,
    snapshot_payload,
)
from .security import Principal
from .source_http import authorize_notebook, problem


def _audit_note(
    deps: ApiDeps,
    principal: Principal,
    *,
    action: AuditAction,
    subject_kind: str,
    subject_id: uuid.UUID,
    details: dict[str, str] | None = None,
) -> None:
    context = current_context()
    deps.audit.record(
        actor_id=principal.user.id,
        action=action.value,
        subject_kind=subject_kind,
        subject_id=subject_id,
        details=details,
        request_id=context.request_id if context is not None else None,
    )


def _snapshot_response(
    note_deps: NoteDeps, snapshot: NoteSnapshot, status_code: int
) -> JSONResponse:
    names = dict(
        note_deps.display_names(
            frozenset({snapshot.note.created_by_user_id, snapshot.revision.author_user_id})
        )
    )
    return JSONResponse(status_code=status_code, content=snapshot_payload(snapshot, names))


def _build_creation_router(
    deps: ApiDeps, principal_dependency: PrincipalDependency, note_deps: NoteDeps
) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/notebooks/{notebook_id}/notes",
        status_code=status.HTTP_201_CREATED,
        response_model=None,
    )
    def create_note(
        notebook_id: uuid.UUID,
        body: CreateNoteRequest,
        principal: Principal = Depends(principal_dependency),
    ) -> JSONResponse:
        denied = authorize_notebook(deps, principal, notebook_id, PolicyAction.NOTE_MUTATE)
        if denied is not None:
            return denied
        snapshot = note_deps.create(
            CreateNoteCommand(principal.user.id, notebook_id, body.title, body.content)
        )
        _audit_note(
            deps,
            principal,
            action=AuditAction.NOTE_CREATED,
            subject_kind="note",
            subject_id=snapshot.note.note_id,
        )
        return _snapshot_response(note_deps, snapshot, status.HTTP_201_CREATED)

    @router.post(
        "/notebooks/{notebook_id}/notes/from-response",
        status_code=status.HTTP_201_CREATED,
        response_model=None,
    )
    def save_response(
        notebook_id: uuid.UUID,
        body: SaveResponseRequest,
        principal: Principal = Depends(principal_dependency),
    ) -> JSONResponse:
        denied = authorize_notebook(deps, principal, notebook_id, PolicyAction.NOTE_MUTATE)
        if denied is not None:
            return denied
        snapshot = note_deps.save_response(
            SaveResponseToNoteCommand(principal.user.id, notebook_id, body.message_id, body.title)
        )
        if snapshot is None:
            return problem(
                "response_not_found",
                "assistant response not found",
                status.HTTP_404_NOT_FOUND,
            )
        _audit_note(
            deps,
            principal,
            action=AuditAction.NOTE_CREATED,
            subject_kind="note",
            subject_id=snapshot.note.note_id,
            details={"kind": snapshot.note.kind.value},
        )
        return _snapshot_response(note_deps, snapshot, status.HTTP_201_CREATED)

    @router.post(
        "/notebooks/{notebook_id}/notes/transforms",
        status_code=status.HTTP_201_CREATED,
        response_model=None,
    )
    def transform_notes(
        notebook_id: uuid.UUID,
        body: TransformNotesRequest,
        principal: Principal = Depends(principal_dependency),
    ) -> JSONResponse:
        denied = authorize_notebook(deps, principal, notebook_id, PolicyAction.NOTE_MUTATE)
        if denied is not None:
            return denied
        try:
            snapshot = note_deps.transform(
                TransformNotesCommand(
                    principal.user.id,
                    notebook_id,
                    body.revision_ids,
                    body.kind,
                    body.title,
                )
            )
        except NoteSelectionError as error:
            return problem(
                "note_selection_invalid",
                str(error),
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        _audit_note(
            deps,
            principal,
            action=AuditAction.NOTE_TRANSFORMED,
            subject_kind="note",
            subject_id=snapshot.note.note_id,
            details={"transform_kind": body.kind.value},
        )
        return _snapshot_response(note_deps, snapshot, status.HTTP_201_CREATED)

    return router


def _build_edit_router(
    deps: ApiDeps, principal_dependency: PrincipalDependency, note_deps: NoteDeps
) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/notes/{note_id}/revisions",
        status_code=status.HTTP_201_CREATED,
        response_model=None,
    )
    def edit_note(
        note_id: uuid.UUID,
        body: EditNoteRequest,
        principal: Principal = Depends(principal_dependency),
        if_match: str = Header(alias="If-Match"),
    ) -> JSONResponse:
        note = note_deps.store.get_note(note_id)
        if note is None:
            return problem("note_not_found", "note not found", status.HTTP_404_NOT_FOUND)
        denied = authorize_notebook(deps, principal, note.notebook_id, PolicyAction.NOTE_MUTATE)
        if denied is not None:
            return denied
        try:
            snapshot = note_deps.edit(
                EditNoteCommand(principal.user.id, note_id, if_match, body.content)
            )
        except NoteConflictError as error:
            return problem("note_conflict", str(error), status.HTTP_409_CONFLICT)
        except NoteNotEditableError as error:
            return problem("note_not_editable", str(error), status.HTTP_409_CONFLICT)
        if snapshot is None:
            return problem("note_not_found", "note not found", status.HTTP_404_NOT_FOUND)
        _audit_note(
            deps,
            principal,
            action=AuditAction.NOTE_REVISION_CREATED,
            subject_kind="note_revision",
            subject_id=snapshot.revision.revision_id,
        )
        return _snapshot_response(note_deps, snapshot, status.HTTP_201_CREATED)

    return router


def _build_promotion_router(
    deps: ApiDeps, principal_dependency: PrincipalDependency, note_deps: NoteDeps
) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/note-revisions/{revision_id}/promote",
        status_code=status.HTTP_201_CREATED,
        response_model=None,
    )
    async def promote_note(
        revision_id: uuid.UUID,
        body: PromoteNoteRequest,
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
            return problem("note_not_found", "note not found", status.HTTP_404_NOT_FOUND)
        denied = authorize_notebook(deps, principal, note.notebook_id, PolicyAction.SOURCE_MUTATE)
        if denied is not None:
            return denied
        try:
            promotion = await note_deps.promote(
                PromoteNoteCommand(principal.user.id, note.notebook_id, revision_id, body.title)
            )
        except NoteSelectionError as error:
            return problem(
                "note_selection_invalid",
                str(error),
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        _audit_note(
            deps,
            principal,
            action=AuditAction.NOTE_PROMOTED,
            subject_kind="source_version",
            subject_id=promotion.source_version_id,
            details={"note_revision_id": str(revision_id)},
        )
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={
                "source_id": str(promotion.source_id),
                "source_version_id": str(promotion.source_version_id),
                "job_id": str(promotion.job_id),
                "created": promotion.created,
            },
        )

    return router


def build_note_mutation_router(
    deps: ApiDeps, principal_dependency: PrincipalDependency, note_deps: NoteDeps
) -> APIRouter:
    """Compose note mutation families under one versioned API router."""
    router = APIRouter()
    router.include_router(_build_creation_router(deps, principal_dependency, note_deps))
    router.include_router(_build_edit_router(deps, principal_dependency, note_deps))
    router.include_router(_build_promotion_router(deps, principal_dependency, note_deps))
    return router
