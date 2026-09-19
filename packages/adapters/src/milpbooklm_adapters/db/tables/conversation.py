"""
Conversation tables: conversations, messages (ch05 "conversations/messages").

ARCH-05-005/006 invariants expressed in DDL:
* a conversation is independent of notebook identity and has an explicit owning user and a
  visibility policy; the private default means notebook membership alone grants no access;
* messages are immutable once committed except for explicit privacy deletion
  (tombstone columns are the only updatable fields - triggers.py enforces this);
* messages pin the exact GenerationInputManifest (NOT NULL FK, ARCH-05-015).
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from ._common import (
    METADATA,
    created_at,
    etag_column,
    revision_column,
    updated_at,
    uuid_fk,
    uuid_pk,
)

conversations = sa.Table(
    "conversations",
    METADATA,
    uuid_pk(),
    # Explicit owning principal: the single source of access truth (ARCH-05-005).
    uuid_fk("owner_user_id", "users"),
    # Context only - notebook identity is NOT part of the conversation identity.
    uuid_fk("notebook_id", "notebooks", nullable=True, ondelete="CASCADE"),
    sa.Column(
        "visibility",
        sa.Text,
        nullable=False,
        server_default=sa.text("'private'"),
    ),
    sa.Column(
        "mode",
        sa.Text,
        nullable=False,
        server_default=sa.text("'ordinary'"),
    ),
    sa.Column(
        "status",
        sa.Text,
        nullable=False,
        server_default=sa.text("'open'"),
        # Reset creates a NEW conversation; it never mutates the old one (ARCH-05-005).
    ),
    revision_column(),
    etag_column(),
    created_at(),
    updated_at(),
    sa.CheckConstraint("status IN ('open', 'reset', 'deleted')", name="ck_conversations_status"),
    sa.CheckConstraint("mode IN ('ordinary', 'agentic')", name="ck_conversations_mode"),
    sa.CheckConstraint("visibility IN ('private', 'shared')", name="ck_conversations_visibility"),
)

messages = sa.Table(
    "messages",
    METADATA,
    uuid_pk(),
    uuid_fk("conversation_id", "conversations", ondelete="CASCADE"),
    uuid_fk("sender_user_id", "users", nullable=True, ondelete="SET NULL"),
    sa.Column(
        "role",
        sa.Text,
        nullable=False,
    ),
    sa.Column("content", sa.Text, nullable=False),
    # The exact pinned manifest keeps past answers explainable after notebook changes.
    uuid_fk("manifest_id", "generation_input_manifests", ondelete="RESTRICT"),
    sa.Column("selected_source_refs", JSONB, nullable=True),
    sa.Column("selected_note_refs", JSONB, nullable=True),
    sa.Column("model_metadata", JSONB, nullable=True),
    sa.Column(
        "provider_status",
        sa.Text,
        nullable=True,
    ),
    sa.Column("tool_trace_refs", JSONB, nullable=True),
    sa.Column("citations", JSONB, nullable=True),
    # Privacy deletion is a tombstone: content removal stays auditable, never silent (ARCH-05-006).
    sa.Column("tombstone_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("tombstone_reason", sa.Text, nullable=True),
    created_at(),
    sa.CheckConstraint("role IN ('user', 'assistant', 'system', 'tool')", name="ck_messages_role"),
    sa.CheckConstraint(
        "provider_status IS NULL OR provider_status IN ('local', 'external', 'refused')",
        name="ck_messages_provider_status",
    ),
    sa.CheckConstraint(
        "(tombstone_at IS NULL) = (tombstone_reason IS NULL)",
        name="ck_messages_tombstone_pair",
    ),
)
