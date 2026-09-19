"""
Conversation / message invariants (ch05 §6, ARCH-05-005/006).

A conversation is independent of notebook identity and has an explicit owning user and a
visibility policy. Notebook membership does NOT imply access to another user's chat history
(the parity default is user-private even inside a shared notebook). Messages are immutable
once committed except for explicit privacy deletion (tombstoning). Resetting creates a NEW
conversation; it never mutates the old one.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum


class ConversationVisibility(StrEnum):
    """PRIVATE is the parity default; SHARED views are deliberate, separate resources."""

    PRIVATE = "private"
    SHARED = "shared"


class ChatMode(StrEnum):
    """ORDINARY (tool-free, notebook-grounded) vs AGENTIC (tool-capable)."""

    ORDINARY = "ordinary"
    AGENTIC = "agentic"


class ConversationStatus(StrEnum):
    """Reset marks the conversation; it never mutates its message history."""

    OPEN = "open"
    RESET = "reset"
    DELETED = "deleted"


@dataclass(frozen=True, slots=True)
class Message:
    """A committed, immutable chat message pinning its exact generation manifest."""

    id: uuid.UUID
    role: str
    content: str
    manifest_id: uuid.UUID
    tombstoned: bool = False


@dataclass(frozen=True, slots=True)
class Conversation:
    """Explicit owner + visibility; notebook_id is context, not identity."""

    id: uuid.UUID
    owner_user_id: uuid.UUID
    notebook_id: uuid.UUID | None
    visibility: ConversationVisibility
    mode: ChatMode
    status: ConversationStatus
    messages: tuple[Message, ...] = ()


def can_access_conversation(
    conversation: Conversation, principal: uuid.UUID, *, is_notebook_member: bool = False
) -> bool:
    """
    Determine conversation access for a principal.

    Access truth is the owner or a deliberately shared conversation; membership alone
    never grants access (ARCH-05-005).
    """
    if conversation.owner_user_id == principal:
        return True
    if conversation.visibility is ConversationVisibility.SHARED:
        return True
    del is_notebook_member  # deliberately unused: membership is NOT an access path
    return False


def reset_conversation(conversation: Conversation, new_id: uuid.UUID) -> Conversation:
    """Reset = a new open conversation for the same owner; the old one is untouched."""
    return Conversation(
        id=new_id,
        owner_user_id=conversation.owner_user_id,
        notebook_id=conversation.notebook_id,
        visibility=conversation.visibility,
        mode=conversation.mode,
        status=ConversationStatus.OPEN,
        messages=(),
    )
