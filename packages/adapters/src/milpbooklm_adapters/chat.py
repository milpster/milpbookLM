"""PostgreSQL implementation of task-17 private conversation operations."""

from __future__ import annotations

import uuid
from threading import Lock

import sqlalchemy as sa
from milpbooklm_application.chat import ChatConfig, ChatMessage, ConversationState

from milpbooklm_adapters.db.tables.conversation import conversations, messages


class PgConversationStore:
    """Own private history and configuration without granting notebook members access."""

    def __init__(self, engine: sa.engine.Engine) -> None:
        """Bind the application-role database engine."""
        self._engine = engine
        self._cancelled: set[tuple[uuid.UUID, uuid.UUID]] = set()
        self._cancellation_lock = Lock()

    def create_conversation(
        self, actor_id: uuid.UUID, notebook_id: uuid.UUID, config: ChatConfig
    ) -> ConversationState:
        """Create a private ordinary conversation owned by the caller."""
        conversation_id = uuid.uuid4()
        with self._engine.begin() as connection:
            _ = connection.execute(
                sa.insert(conversations).values(
                    id=conversation_id,
                    owner_user_id=actor_id,
                    notebook_id=notebook_id,
                    chat_config=_config(config),
                )
            )
        state = self.get_authoritative_state(actor_id, conversation_id)
        if state is None:
            raise LookupError("created conversation is unavailable")
        return state

    def get_authoritative_state(
        self, actor_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> ConversationState | None:
        """Load only open, private conversations owned by the requesting actor."""
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(conversations).where(
                        conversations.c.id == conversation_id,
                        conversations.c.owner_user_id == actor_id,
                        conversations.c.visibility == "private",
                        conversations.c.status == "open",
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            history = (
                connection.execute(
                    sa.select(messages)
                    .where(
                        messages.c.conversation_id == conversation_id,
                        messages.c.tombstone_at.is_(None),
                    )
                    .order_by(messages.c.created_at)
                )
                .mappings()
                .all()
            )
        config = row["chat_config"]
        return ConversationState(
            conversation_id,
            row["notebook_id"],
            ChatConfig(config["style"], config["length"], config["output_language"]),
            row["instructions"],
            tuple(
                ChatMessage(
                    item["id"],
                    item["role"],
                    item["content"],
                    item["manifest_id"],
                    tuple(item["citations"] or ()),
                )
                for item in history
            ),
        )

    def update_config(
        self, actor_id: uuid.UUID, conversation_id: uuid.UUID, config: ChatConfig
    ) -> ConversationState | None:
        """Persist future-turn response preferences for an owned conversation."""
        with self._engine.begin() as connection:
            _ = connection.execute(
                sa.update(conversations)
                .where(
                    conversations.c.id == conversation_id,
                    conversations.c.owner_user_id == actor_id,
                    conversations.c.visibility == "private",
                    conversations.c.status == "open",
                )
                .values(chat_config=_config(config))
            )
        return self.get_authoritative_state(actor_id, conversation_id)

    def update_instructions(
        self, actor_id: uuid.UUID, conversation_id: uuid.UUID, instructions: str
    ) -> ConversationState | None:
        """Persist instructions for inclusion in later frozen manifests."""
        with self._engine.begin() as connection:
            _ = connection.execute(
                sa.update(conversations)
                .where(
                    conversations.c.id == conversation_id,
                    conversations.c.owner_user_id == actor_id,
                    conversations.c.visibility == "private",
                    conversations.c.status == "open",
                )
                .values(instructions=instructions)
            )
        return self.get_authoritative_state(actor_id, conversation_id)

    def reset(self, actor_id: uuid.UUID, conversation_id: uuid.UUID) -> ConversationState | None:
        """Close the old history and return a new empty private conversation."""
        new_id = uuid.uuid4()
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(
                        conversations.c.notebook_id,
                        conversations.c.chat_config,
                        conversations.c.instructions,
                    ).where(
                        conversations.c.id == conversation_id,
                        conversations.c.owner_user_id == actor_id,
                        conversations.c.visibility == "private",
                        conversations.c.status == "open",
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            _ = connection.execute(
                sa.update(conversations)
                .where(conversations.c.id == conversation_id)
                .values(status="reset")
            )
            _ = connection.execute(
                sa.insert(conversations).values(
                    id=new_id,
                    owner_user_id=actor_id,
                    notebook_id=row["notebook_id"],
                    chat_config=row["chat_config"],
                    instructions=row["instructions"],
                )
            )
        self.clear_cancel(actor_id, conversation_id)
        return self.get_authoritative_state(actor_id, new_id)

    def delete(self, actor_id: uuid.UUID, conversation_id: uuid.UUID) -> bool:
        """Hide an owned conversation by moving it to its terminal status."""
        with self._engine.begin() as connection:
            result = connection.execute(
                sa.update(conversations)
                .where(
                    conversations.c.id == conversation_id,
                    conversations.c.owner_user_id == actor_id,
                    conversations.c.visibility == "private",
                    conversations.c.status == "open",
                )
                .values(status="deleted")
            )
        return result.rowcount == 1

    def append_user_message(
        self, actor_id: uuid.UUID, conversation_id: uuid.UUID, manifest_id: uuid.UUID, content: str
    ) -> uuid.UUID | None:
        """Insert a manifest-backed message under the ownership check in one statement."""
        message_id = uuid.uuid4()
        with self._engine.begin() as connection:
            return connection.execute(
                sa.insert(messages).from_select(
                    (
                        "id",
                        "conversation_id",
                        "sender_user_id",
                        "role",
                        "content",
                        "manifest_id",
                        "provider_status",
                        "tool_trace_refs",
                    ),
                    sa.select(
                        sa.literal(message_id),
                        conversations.c.id,
                        sa.literal(actor_id),
                        sa.literal("user"),
                        sa.literal(content),
                        sa.literal(manifest_id),
                        sa.literal("local"),
                        sa.literal([], type_=sa.JSON),
                    ).where(
                        conversations.c.id == conversation_id,
                        conversations.c.owner_user_id == actor_id,
                        conversations.c.visibility == "private",
                        conversations.c.status == "open",
                    ),
                ).returning(messages.c.id)
            ).scalar_one_or_none()

    def cancel(self, actor_id: uuid.UUID, conversation_id: uuid.UUID) -> bool:
        """Mark an owned open conversation's active presentation as cancelled."""
        if self.get_authoritative_state(actor_id, conversation_id) is None:
            return False
        with self._cancellation_lock:
            self._cancelled.add((actor_id, conversation_id))
        return True

    def cancelled(self, actor_id: uuid.UUID, conversation_id: uuid.UUID) -> bool:
        """Read the process-local cancellation signal between streamed chunks."""
        with self._cancellation_lock:
            return (actor_id, conversation_id) in self._cancelled

    def clear_cancel(self, actor_id: uuid.UUID, conversation_id: uuid.UUID) -> None:
        """Discard a terminal turn's process-local cancellation signal."""
        with self._cancellation_lock:
            self._cancelled.discard((actor_id, conversation_id))


def _config(config: ChatConfig) -> dict[str, str]:
    return {
        "style": config.style,
        "length": config.length,
        "output_language": config.output_language,
    }
