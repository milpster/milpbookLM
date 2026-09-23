"""
Policy-filtered notebook routes.

The query layer (list) and the handler layer (object check with a stable 403
reason) both enforce authorization through the same policy engine - no
permission logic lives in route conditionals.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from milpbooklm_application.audit_actions import AuditAction
from milpbooklm_application.policy_engine import NotebookAccess
from milpbooklm_domain.policy import PolicyAction
from pydantic import BaseModel, ConfigDict, Field
from starlette import status

from .deps import ApiDeps, PrincipalDependency
from .security import Principal
from .source_http import problem


def _not_found() -> JSONResponse:
    """Return the uniform 404 for an unknown notebook."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={"detail": "notebook not found"}
    )


def _denied(reason: str) -> JSONResponse:
    """Return the handler-level 403 carrying the engine's stable reason code."""
    return JSONResponse(status_code=403, content={"detail": {"reason": reason}})


def _view_payload(
    notebook_id: uuid.UUID, title: str, custody_state: str, membership: str | None
) -> dict[str, object]:
    """Return the uniform JSON shape of one visible notebook row."""
    return {
        "notebook_id": str(notebook_id),
        "title": title,
        "custody_state": custody_state,
        "membership": membership,
    }


class CreateNotebookRequest(BaseModel):
    """One notebook creation command (title only; sharing is a later COL-01 surface)."""

    model_config = ConfigDict(frozen=True)

    title: str = Field(min_length=1, max_length=300)


def _build_read_router(deps: ApiDeps, principal: PrincipalDependency) -> APIRouter:
    """Query-layer read surface (list + one notebook with the handler object check)."""
    router = APIRouter(prefix="/api/v1/notebooks", tags=["notebooks"])

    @router.get("")
    async def list_notebooks(
        principal: Principal = Depends(principal),
    ) -> list[dict[str, object]]:
        """Return the user's notebooks (query-layer filter: membership only)."""
        return [
            _view_payload(
                view.notebook_id,
                view.title,
                view.custody_state,
                view.membership.value if view.membership is not None else None,
            )
            for view in deps.notebooks.visible_notebooks(principal.user.id)
        ]

    @router.get("/{notebook_id}", response_model=None)
    async def get_notebook(
        notebook_id: uuid.UUID, principal: Principal = Depends(principal)
    ) -> JSONResponse | dict[str, object]:
        """One notebook with the handler-level object check (403 with reason on deny)."""
        view = deps.notebooks.notebook_with_membership(principal.user.id, notebook_id)
        if view is None:
            return _not_found()
        access = NotebookAccess(notebook_id=view.notebook_id, role=view.membership)
        decision = deps.engine.decide_notebook(principal.user, access, PolicyAction.READ_CONTENT)
        if not decision.allowed:
            return _denied(decision.reason.value)
        return _view_payload(
            view.notebook_id,
            view.title,
            view.custody_state,
            view.membership.value if view.membership is not None else None,
        )

    return router


def _build_mutation_router(deps: ApiDeps, principal: PrincipalDependency) -> APIRouter:
    """Build notebook creation; note mutations live on the real note router."""
    router = APIRouter(prefix="/api/v1/notebooks", tags=["notebooks"])

    @router.post("", response_model=None, status_code=status.HTTP_201_CREATED)
    async def create_notebook(
        body: CreateNotebookRequest,
        principal: Principal = Depends(principal),
    ) -> JSONResponse:
        """Create a private notebook owned by the actor (ch05 owner-membership invariant)."""
        if deps.notebook_store is None:
            return problem(
                "notebook_creation_unavailable",
                "notebook creation is not configured for this installation",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        title = body.title.strip()
        if not title:
            return problem("invalid_title", "notebook title must be non-empty", 422)
        view = deps.notebook_store.create(title=title, actor_id=principal.user.id)
        deps.audit.record(
            actor_id=principal.user.id,
            action=AuditAction.NOTEBOOK_CREATED.value,
            subject_kind="notebook",
            subject_id=view.notebook_id,
        )
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=_view_payload(
                view.notebook_id,
                view.title,
                view.custody_state,
                view.membership.value if view.membership is not None else None,
            ),
        )

    return router


def build_notebook_router(deps: ApiDeps, principal: PrincipalDependency) -> APIRouter:
    """Build the /api/v1/notebooks router over the wired dependencies."""
    router = APIRouter()
    router.include_router(_build_read_router(deps, principal))
    router.include_router(_build_mutation_router(deps, principal))
    return router
