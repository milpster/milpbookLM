"""Citation-jump surface for already published grounded answers."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from milpbooklm_application.grounding import GroundingError
from starlette import status

from .deps import ApiDeps, PrincipalDependency
from .security import Principal
from .source_http import problem


def build_grounding_router(deps: ApiDeps, principal_dependency: PrincipalDependency) -> APIRouter:
    """Build pinned citation resolution without task-17 conversation endpoints."""
    router = APIRouter(prefix="/api/v1/source-versions", tags=["grounding"])

    @router.get("/{source_version_id}/nodes/{canonical_node_id}", response_model=None)
    def citation_jump(
        source_version_id: uuid.UUID,
        canonical_node_id: uuid.UUID,
        principal: Principal = Depends(principal_dependency),
    ) -> JSONResponse:
        if deps.grounding is None:
            return problem(
                "grounding_unavailable",
                "citation resolution is not configured for this installation",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        try:
            resolved = deps.grounding.jump(
                actor_user_id=principal.user.id,
                source_version_id=source_version_id,
                canonical_node_id=canonical_node_id,
            )
        except GroundingError:
            return problem(
                "citation_not_found", "citation is unavailable", status.HTTP_404_NOT_FOUND
            )
        return JSONResponse(content=resolved)

    return router
