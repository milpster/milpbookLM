"""Ordinary private chat routes and best-effort SSE presentation."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from typing import Final

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from milpbooklm_application.chat import (
    ChatConfig,
    ConversationState,
    ConversationStore,
    GenerateChatTurn,
)
from milpbooklm_application.grounding import GroundedAnswer
from milpbooklm_domain.policy import PolicyAction
from pydantic import BaseModel, ConfigDict, Field

from .deps import ApiDeps, PrincipalDependency
from .security import Principal
from .source_http import authorize_notebook, problem

_HTTP_OK: Final = 200


class ConversationRequest(BaseModel):
    """Validated request to create an actor-private ordinary conversation."""

    model_config = ConfigDict(frozen=True)
    notebook_id: uuid.UUID
    style: str = Field(default="standard", pattern="^(standard|learning|custom)$")
    length: str = Field(default="default", pattern="^(shorter|default|longer)$")
    output_language: str = Field(default="EN", pattern="^(DE|EN)$")


class TurnRequest(BaseModel):
    """Validated content and explicit note selections for one grounded turn."""

    model_config = ConfigDict(frozen=True)
    content: str = Field(min_length=1, max_length=10_000)
    selected_note_revision_ids: tuple[uuid.UUID, ...] = ()


class ChatConfigRequest(BaseModel):
    """Validated configuration for subsequent ordinary-chat turns."""

    model_config = ConfigDict(frozen=True)
    style: str = Field(default="standard", pattern="^(standard|learning|custom)$")
    length: str = Field(default="default", pattern="^(shorter|default|longer)$")
    output_language: str = Field(default="EN", pattern="^(DE|EN)$")


class InstructionsRequest(BaseModel):
    """Validated instructions that will be pinned into subsequent manifests."""

    model_config = ConfigDict(frozen=True)
    instructions: str = Field(max_length=10_000)


def _state(state: ConversationState) -> dict[str, object]:
    return {
        "id": str(state.id),
        "notebook_id": str(state.notebook_id),
        "config": {
            "style": state.config.style,
            "length": state.config.length,
            "output_language": state.config.output_language,
        },
        "instructions": state.instructions,
        "messages": [
            {
                "id": str(item.id),
                "role": item.role,
                "content": item.content,
                "manifest_id": str(item.manifest_id),
                "citations": item.citations,
            }
            for item in state.messages
        ],
    }


def build_conversation_router(
    deps: ApiDeps, principal_dependency: PrincipalDependency
) -> APIRouter:
    """Compose small route families for private ordinary chat."""
    router = APIRouter(prefix="/api/v1", tags=["conversations"])
    router.include_router(_build_lifecycle_router(deps, principal_dependency))
    router.include_router(_build_generation_router(deps, principal_dependency))
    return router


def _unavailable(deps: ApiDeps) -> JSONResponse | None:
    if deps.conversations is None:
        return problem("chat_unavailable", "ordinary chat is not configured", 503)
    return None


def _conversation_store(deps: ApiDeps) -> ConversationStore:
    """Return the configured store after the route's availability boundary."""
    if deps.conversations is None:
        raise RuntimeError("conversation store is unavailable")
    return deps.conversations


def _chat_turn(deps: ApiDeps) -> GenerateChatTurn:
    """Return the configured use case after its route availability boundary."""
    if deps.chat_turn is None:
        raise RuntimeError("chat turn is unavailable")
    return deps.chat_turn


def _build_lifecycle_router(  # noqa: C901
    deps: ApiDeps, principal_dependency: PrincipalDependency
) -> APIRouter:
    router = APIRouter()

    @router.post("/conversations", status_code=201)
    def create(
        body: ConversationRequest, principal: Principal = Depends(principal_dependency)
    ) -> JSONResponse:
        denied = authorize_notebook(
            deps, principal, body.notebook_id, PolicyAction.CHAT_GROUNDED_PRIVATE
        )
        if denied is not None:
            return denied
        unavailable = _unavailable(deps)
        if unavailable is not None:
            return unavailable
        state = _conversation_store(deps).create_conversation(
            principal.user.id,
            body.notebook_id,
            ChatConfig(body.style, body.length, body.output_language),
        )
        return JSONResponse(status_code=201, content=_state(state))

    @router.get("/conversations/{conversation_id}")
    def state(
        conversation_id: uuid.UUID, principal: Principal = Depends(principal_dependency)
    ) -> JSONResponse:
        unavailable = _unavailable(deps)
        if unavailable is not None:
            return unavailable
        result = _conversation_store(deps).get_authoritative_state(
            principal.user.id, conversation_id
        )
        if result is None:
            return problem("conversation_not_found", "conversation not found", 404)
        return JSONResponse(content=_state(result))

    @router.put("/conversations/{conversation_id}/config")
    def config(
        conversation_id: uuid.UUID,
        body: ChatConfigRequest,
        principal: Principal = Depends(principal_dependency),
    ) -> JSONResponse:
        unavailable = _unavailable(deps)
        if unavailable is not None:
            return unavailable
        result = _conversation_store(deps).update_config(
            principal.user.id,
            conversation_id,
            ChatConfig(body.style, body.length, body.output_language),
        )
        if result is None:
            return problem("conversation_not_found", "conversation not found", 404)
        return JSONResponse(content=_state(result))

    @router.put("/conversations/{conversation_id}/instructions")
    def instructions(
        conversation_id: uuid.UUID,
        body: InstructionsRequest,
        principal: Principal = Depends(principal_dependency),
    ) -> JSONResponse:
        unavailable = _unavailable(deps)
        if unavailable is not None:
            return unavailable
        result = _conversation_store(deps).update_instructions(
            principal.user.id, conversation_id, body.instructions
        )
        if result is None:
            return problem("conversation_not_found", "conversation not found", 404)
        return JSONResponse(content=_state(result))

    @router.post("/conversations/{conversation_id}/reset")
    def reset(
        conversation_id: uuid.UUID, principal: Principal = Depends(principal_dependency)
    ) -> JSONResponse:
        unavailable = _unavailable(deps)
        if unavailable is not None:
            return unavailable
        result = _conversation_store(deps).reset(principal.user.id, conversation_id)
        if result is None:
            return problem("conversation_not_found", "conversation not found", 404)
        return JSONResponse(content=_state(result))

    @router.delete("/conversations/{conversation_id}", status_code=204)
    def delete(
        conversation_id: uuid.UUID, principal: Principal = Depends(principal_dependency)
    ) -> JSONResponse:
        unavailable = _unavailable(deps)
        if unavailable is not None:
            return unavailable
        if not _conversation_store(deps).delete(principal.user.id, conversation_id):
            return problem("conversation_not_found", "conversation not found", 404)
        return JSONResponse(status_code=204, content=None)

    return router


def _answer_payload(answer: GroundedAnswer, state: ConversationState | None) -> dict[str, object]:
    """Build the terminal authoritative REST-equivalent response shape."""
    return {
        "answer_message_id": str(answer.message_id) if answer.message_id else None,
        "manifest_id": str(answer.manifest_id),
        "insufficient_evidence": answer.insufficient_evidence,
        "state": _state(state) if state else None,
        "tool_trace": [],
        "disclosure": None,
        "provider_dispatch": {
            "locality": "local",
            "external_dispatches": [],
            "disclosure_events": [],
        },
    }


def _build_generation_router(  # noqa: C901
    deps: ApiDeps, principal_dependency: PrincipalDependency
) -> APIRouter:
    router = APIRouter()

    @router.post("/conversations/{conversation_id}/messages")
    def turn(
        conversation_id: uuid.UUID,
        body: TurnRequest,
        principal: Principal = Depends(principal_dependency),
    ) -> JSONResponse:
        if deps.chat_turn is None:
            return problem("chat_unavailable", "ordinary chat is not configured", 503)
        answer = deps.chat_turn(
            principal.user.id, conversation_id, body.content, body.selected_note_revision_ids
        )
        if answer is None:
            return problem("conversation_not_found", "conversation not found", 404)
        state = (
            _conversation_store(deps).get_authoritative_state(principal.user.id, conversation_id)
            if deps.conversations
            else None
        )
        return JSONResponse(content=_answer_payload(answer, state))

    @router.post("/conversations/{conversation_id}/messages/stream", response_model=None)
    def stream(
        conversation_id: uuid.UUID,
        body: TurnRequest,
        principal: Principal = Depends(principal_dependency),
    ) -> StreamingResponse | JSONResponse:
        if deps.chat_turn is None or deps.conversations is None:
            return problem("chat_unavailable", "ordinary chat is not configured", 503)
        if (
            _conversation_store(deps).get_authoritative_state(principal.user.id, conversation_id)
            is None
        ):
            return problem("conversation_not_found", "conversation not found", 404)

        def events() -> Iterator[str]:
            generation = _chat_turn(deps).stream(
                principal.user.id, conversation_id, body.content, body.selected_note_revision_ids
            )
            while True:
                try:
                    token = next(generation)
                except StopIteration as finished:
                    answer = finished.value
                    if answer is None:
                        yield "event: cancelled\ndata: {}\n\n"
                    else:
                        state = _conversation_store(deps).get_authoritative_state(
                            principal.user.id, conversation_id
                        )
                        terminal = json.dumps(_answer_payload(answer, state))
                        yield f"event: terminal\ndata: {terminal}\n\n"
                    return
                yield f"event: token\ndata: {json.dumps({'token': token})}\n\n"

        return StreamingResponse(
            events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
        )

    @router.post("/conversations/{conversation_id}/cancel")
    def cancel(
        conversation_id: uuid.UUID, principal: Principal = Depends(principal_dependency)
    ) -> JSONResponse:
        unavailable = _unavailable(deps)
        if unavailable is not None:
            return unavailable
        if not _conversation_store(deps).cancel(principal.user.id, conversation_id):
            return problem("conversation_not_found", "conversation not found", 404)
        return JSONResponse(content={"cancelled": True})

    return router
