"""
Generation input manifest tables (ch05 §9, ARCH-05-015/016).

Every committed model-generated output pins exactly one immutable manifest. A materialized
manifest never changes: retrieval/index updates, note edits, artifact revisions, instruction
or preference changes, conversation resets, connector refreshes and later tool results MUST
NOT silently change it (immutability triggers in triggers.py). Agent runs create new child
manifests (parent_manifest_id) that reference newly acquired immutable results.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from ._common import METADATA, created_at, uuid_fk, uuid_pk

generation_input_manifests = sa.Table(
    "generation_input_manifests",
    METADATA,
    uuid_pk(),
    uuid_fk("notebook_id", "notebooks", nullable=True, ondelete="SET NULL"),
    uuid_fk("created_by_user_id", "users", nullable=True, ondelete="SET NULL"),
    # A later agent generation deliberately creates a child manifest (ARCH-05-016).
    uuid_fk("parent_manifest_id", "generation_input_manifests", nullable=True, ondelete="SET NULL"),
    sa.Column(
        "op_kind",
        sa.Text,
        nullable=False,
    ),
    # Resolved generation-configuration snapshot: instructions as applied, style/mode,
    # output language, material feature flags (ARCH-05-015).
    sa.Column("config_snapshot", JSONB, nullable=False),
    # Exact prior message ids/content hashes included as conversation context.
    sa.Column("context_snapshot", JSONB, nullable=True),
    sa.Column("retrieval_version", sa.Text, nullable=True),
    sa.Column("retrieval_settings", JSONB, nullable=True),
    sa.Column("template_version", sa.Text, nullable=True),
    sa.Column("model_role_requests", JSONB, nullable=True),
    created_at(),
    sa.CheckConstraint(
        "op_kind IN ('ordinary_chat', 'agentic_chat', 'studio_generation', 'research_step', "
        "'note_transformation', 'study_followup')",
        name="ck_generation_input_manifests_op_kind",
    ),
)

generation_manifest_items = sa.Table(
    "generation_manifest_items",
    METADATA,
    uuid_pk(),
    uuid_fk("manifest_id", "generation_input_manifests", ondelete="CASCADE"),
    # item_id is polymorphic (references the named entity's id); the kind column names
    # which table it lives in - a foreign key per kind would prevent one clean item row.
    sa.Column(
        "item_kind",
        sa.Text,
        nullable=False,
    ),
    sa.Column("item_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("item_sha256", sa.Text, nullable=True),
    sa.Column("meta", JSONB, nullable=True),
    created_at(),
    sa.UniqueConstraint(
        "manifest_id",
        "item_kind",
        "item_id",
        name="uq_generation_manifest_items_manifest_kind_item",
    ),
    sa.CheckConstraint(
        "item_kind IN ('source_version', 'canonical_document', 'note_revision', "
        "'artifact_version', 'study_session_snapshot', 'message', 'tool_result', "
        "'evidence_snapshot')",
        name="ck_generation_manifest_items_kind",
    ),
)
