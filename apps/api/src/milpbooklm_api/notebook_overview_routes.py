"""Grounded notebook overview HTTP surface."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from milpbooklm_application.chat import ChatMessage, NotebookOverview
from milpbooklm_application.grounding import GroundedAnswer
from milpbooklm_domain.policy import PolicyAction
from pydantic import BaseModel, ConfigDict, Field

from .deps import ApiDeps, PrincipalDependency
from .security import Principal
from .source_http import authorize_notebook, problem


class OverviewRequest(BaseModel):
    """Validated notebook-overview output preferences."""

    model_config = ConfigDict(frozen=True)
    output_language: str = Field(default="EN", pattern="^(DE|EN)$")


def _message(overview: NotebookOverview, answer: GroundedAnswer) -> ChatMessage | None:
    if answer.message_id is None:
        return None
    return next(
        (message for message in overview.conversation.messages if message.id == answer.message_id),
        None,
    )


def _grounded_output(overview: NotebookOverview, answer: GroundedAnswer) -> dict[str, object]:
    message = _message(overview, answer)
    return {
        "message_id": str(answer.message_id) if answer.message_id else None,
        "manifest_id": str(answer.manifest_id),
        "content": message.content if message else "",
        "citations": message.citations if message else (),
        "insufficient_evidence": answer.insufficient_evidence,
    }


def build_notebook_overview_router(
    deps: ApiDeps, principal_dependency: PrincipalDependency
) -> APIRouter:
    """Expose private summary and suggested-question generation for one notebook."""
    router = APIRouter(prefix="/api/v1", tags=["notebook-overview"])

    @router.post("/notebooks/{notebook_id}/overview")
    def generate(
        notebook_id: uuid.UUID,
        body: OverviewRequest,
        principal: Principal = Depends(principal_dependency),
    ) -> JSONResponse:
        denied = authorize_notebook(
            deps, principal, notebook_id, PolicyAction.CHAT_GROUNDED_PRIVATE
        )
        if denied is not None:
            return denied
        if deps.notebook_overview is None:
            return problem("chat_unavailable", "notebook overview is not configured", 503)
        overview = deps.notebook_overview(
            principal.user.id,
            notebook_id,
            body.output_language,
        )
        questions = _grounded_output(overview, overview.suggested_questions)
        return JSONResponse(
            content={
                "conversation_id": str(overview.conversation.id),
                "summary": _grounded_output(overview, overview.summary),
                "suggested_questions": [
                    {
                        "question": span.text,
                        "citations": questions["citations"],
                    }
                    for span in overview.suggested_questions.spans
                ],
                "tool_trace": [],
                "disclosure": None,
                "provider_dispatch": {
                    "locality": "local",
                    "external_dispatches": [],
                    "disclosure_events": [],
                },
            }
        )

    return router
