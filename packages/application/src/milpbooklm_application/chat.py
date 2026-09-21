"""Application-owned ordinary chat lifecycle and manifest-backed turns."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from dataclasses import dataclass
from typing import Protocol

from milpbooklm_application.grounding import (
    GenerateGroundedAnswer,
    GroundedAnswer,
    GroundingRequest,
)


@dataclass(frozen=True, slots=True)
class ChatConfig:
    """The user-visible response preferences pinned into new chat manifests."""

    style: str = "standard"
    length: str = "default"
    output_language: str = "EN"


@dataclass(frozen=True, slots=True)
class ConversationState:
    """Authoritative private history returned after an SSE reconnect."""

    id: uuid.UUID
    notebook_id: uuid.UUID
    config: ChatConfig
    instructions: str
    messages: tuple[ChatMessage, ...]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """A persisted message; citations are server-resolved final state only."""

    id: uuid.UUID
    role: str
    content: str
    manifest_id: uuid.UUID
    citations: tuple[dict[str, str | int], ...]


@dataclass(frozen=True, slots=True)
class NotebookOverview:
    """A private grounded summary and grounded starting-question set."""

    conversation: ConversationState
    summary: GroundedAnswer
    suggested_questions: GroundedAnswer


class ConversationStore(Protocol):
    """Private conversation persistence boundary."""

    def create_conversation(
        self, actor_id: uuid.UUID, notebook_id: uuid.UUID, config: ChatConfig
    ) -> ConversationState:
        """Create an actor-owned, private ordinary conversation."""
        ...

    def get_authoritative_state(
        self, actor_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> ConversationState | None:
        """Return the actor's private persisted history."""
        ...

    def update_config(
        self, actor_id: uuid.UUID, conversation_id: uuid.UUID, config: ChatConfig
    ) -> ConversationState | None:
        """Persist user-visible configuration for later turns."""
        ...

    def update_instructions(
        self, actor_id: uuid.UUID, conversation_id: uuid.UUID, instructions: str
    ) -> ConversationState | None:
        """Persist instructions which are pinned into subsequent manifests."""
        ...

    def reset(self, actor_id: uuid.UUID, conversation_id: uuid.UUID) -> ConversationState | None:
        """Clear private history without changing notebook access."""
        ...

    def delete(self, actor_id: uuid.UUID, conversation_id: uuid.UUID) -> bool:
        """Remove the conversation from its owner's visible state."""
        ...

    def append_user_message(
        self,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        manifest_id: uuid.UUID,
        content: str,
    ) -> uuid.UUID | None:
        """Atomically associate the new user message with its frozen manifest."""
        ...

    def cancel(self, actor_id: uuid.UUID, conversation_id: uuid.UUID) -> bool:
        """Request cancellation of the currently generating turn, if any."""
        ...

    def cancelled(self, actor_id: uuid.UUID, conversation_id: uuid.UUID) -> bool:
        """Report whether the active turn has been cancelled."""
        ...

    def clear_cancel(self, actor_id: uuid.UUID, conversation_id: uuid.UUID) -> None:
        """Clear a completed turn's transient cancellation marker."""
        ...


class GenerateChatTurn:
    """Freeze and persist a user turn before delegating assistant publication to T16."""

    def __init__(self, store: ConversationStore, grounding: GenerateGroundedAnswer) -> None:
        """Bind the private history and validated grounding seams."""
        self._store = store
        self._grounding = grounding

    def __call__(
        self,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        question: str,
        selected_notes: tuple[uuid.UUID, ...] = (),
    ) -> GroundedAnswer | None:
        """Freeze and persist one user turn before validated assistant publication."""
        state = self._store.get_authoritative_state(actor_id, conversation_id)
        if state is None:
            return None
        request = GroundingRequest(
            actor_user_id=actor_id,
            notebook_id=state.notebook_id,
            conversation_id=conversation_id,
            question=question,
            context_message_ids=tuple(item.id for item in state.messages),
            selected_note_revision_ids=selected_notes,
            chat_config_snapshot={
                "style": state.config.style,
                "length": state.config.length,
                "output_language": state.config.output_language,
            },
            instructions_snapshot=state.instructions,
        )
        manifest = self._grounding.freeze(request)
        user_message = self._store.append_user_message(
            actor_id,
            conversation_id,
            manifest.id,
            question,
        )
        if user_message is None:
            return None
        return self._grounding.generate(request, manifest)

    def stream(
        self,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        question: str,
        selected_notes: tuple[uuid.UUID, ...] = (),
    ) -> Generator[str, None, GroundedAnswer | None]:
        """Yield tokens and return only a validated persisted final answer."""
        state = self._store.get_authoritative_state(actor_id, conversation_id)
        if state is None:
            return None
        request = GroundingRequest(
            actor_user_id=actor_id,
            notebook_id=state.notebook_id,
            conversation_id=conversation_id,
            question=question,
            context_message_ids=tuple(item.id for item in state.messages),
            selected_note_revision_ids=selected_notes,
            chat_config_snapshot={
                "style": state.config.style,
                "length": state.config.length,
                "output_language": state.config.output_language,
            },
            instructions_snapshot=state.instructions,
        )
        manifest = self._grounding.freeze(request)
        appended = self._store.append_user_message(actor_id, conversation_id, manifest.id, question)
        if appended is None:
            return None
        try:
            answer = yield from self._grounding.stream_generate(
                request,
                manifest,
                lambda: self._store.cancelled(actor_id, conversation_id),
            )
            return answer
        finally:
            self._store.clear_cancel(actor_id, conversation_id)


class GenerateNotebookOverview:
    """Generate notebook orientation through the same validated grounded pipeline as chat."""

    def __init__(self, store: ConversationStore, turn: GenerateChatTurn) -> None:
        """Bind private conversation persistence and ordinary grounded generation."""
        self._store = store
        self._turn = turn

    def __call__(
        self, actor_id: uuid.UUID, notebook_id: uuid.UUID, output_language: str
    ) -> NotebookOverview:
        """Create a private overview conversation and publish both grounded outputs."""
        conversation = self._store.create_conversation(
            actor_id,
            notebook_id,
            ChatConfig(length="shorter", output_language=output_language),
        )
        summary = self._turn(
            actor_id,
            conversation.id,
            "Summarize this notebook from its sources.",
        )
        questions = self._turn(
            actor_id,
            conversation.id,
            "Suggest three grounded starting questions about this notebook.",
        )
        if summary is None or questions is None:
            raise RuntimeError("overview conversation became unavailable")
        state = self._store.get_authoritative_state(actor_id, conversation.id)
        if state is None:
            raise RuntimeError("overview conversation became unavailable")
        return NotebookOverview(state, summary, questions)
