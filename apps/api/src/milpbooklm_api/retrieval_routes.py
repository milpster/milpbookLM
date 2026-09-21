"""Hybrid knowledge search endpoint (IDX-01, CP2): POST /notebooks/{id}/search."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from milpbooklm_application.retrieval import (
    MAX_TOP_K,
    RetrievalCommand,
    RetrievalUnavailableError,
)
from milpbooklm_domain.policy import PolicyAction
from pydantic import BaseModel, ConfigDict, Field
from starlette import status

from .deps import ApiDeps, PrincipalDependency
from .security import Principal
from .source_http import authorize_notebook, problem


class SearchRequest(BaseModel):
    """One hybrid retrieval request against the notebook's indexed sources."""

    model_config = ConfigDict(frozen=True)

    query: str = Field(min_length=1, max_length=1000)
    mode: str = Field(default="fused", pattern="^(lexical|vector|fused)$")
    top_k: int = Field(default=10, ge=1, le=MAX_TOP_K)
    language: str | None = Field(default=None, max_length=8)
    source_ids: tuple[uuid.UUID, ...] | None = Field(default=None, max_length=50)


def build_retrieval_router(
    deps: ApiDeps, principal_dependency: PrincipalDependency
) -> APIRouter:
    """Build the notebook-scoped search route (authz: notebook READ_CONTENT)."""
    router = APIRouter(prefix="/api/v1/notebooks", tags=["retrieval"])

    @router.post("/{notebook_id}/search", response_model=None)
    def search_notebook(
        notebook_id: uuid.UUID,
        body: SearchRequest,
        principal: Principal = Depends(principal_dependency),
    ) -> JSONResponse:
        denied = authorize_notebook(deps, principal, notebook_id, PolicyAction.READ_CONTENT)
        if denied is not None:
            return denied
        if deps.retrieval is None:
            return problem(
                "retrieval_unavailable",
                "hybrid search is not configured for this installation",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        command = RetrievalCommand(
            actor_user_id=principal.user.id,
            notebook_id=notebook_id,
            query=body.query,
            language=body.language,
            mode=body.mode,
            top_k=body.top_k,
            source_ids=frozenset(body.source_ids) if body.source_ids else None,
        )
        try:
            outcome = deps.retrieval(command)
        except RetrievalUnavailableError:
            return problem(
                "vector_retrieval_unavailable",
                "vector retrieval requires an embedding endpoint (lexical mode is available)",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return JSONResponse(
            content={
                "mode": outcome.mode,
                "fusion_config_version": outcome.fusion_config_version,
                "results": [
                    {
                        "chunk_id": str(entry.row.chunk_id),
                        "source_id": str(entry.row.source_id),
                        "source_version_id": str(entry.row.source_version_id),
                        "source_title": entry.row.source_title,
                        "canonical_node_id": str(entry.row.canonical_node_id),
                        "char_start": entry.row.char_start,
                        "char_end": entry.row.char_end,
                        "text": entry.row.text,
                        "language": entry.row.language,
                        "score": entry.score,
                        "rank": entry.rank,
                        "retriever_scores": entry.retriever_scores,
                        "retriever_ranks": entry.retriever_ranks,
                    }
                    for entry in outcome.results
                ],
            }
        )

    return router
