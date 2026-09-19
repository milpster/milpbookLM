"""
Blob, audit and lifecycle tables (ch05 "blob_objects/references", "purge_tasks", "audit_events").

Blob writes follow the crash-consistent finalize protocol: objects start in staging and are
finalized exactly once (state check constraint); references track every content-bearing user
of an object so AD-016 purge traversal can find them. Audit events are append-only.
migration_metadata is the harness's build-metadata store (ch04 "records build metadata").
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from ._common import METADATA, created_at, updated_at, uuid_fk, uuid_pk

blob_objects = sa.Table(
    "blob_objects",
    METADATA,
    uuid_pk(),
    sa.Column("content_sha256", sa.Text, nullable=False, unique=True),
    sa.Column("size_bytes", sa.BigInteger, nullable=False),
    sa.Column("content_type", sa.Text, nullable=True),
    sa.Column("storage_path", sa.Text, nullable=False),
    sa.Column(
        "state",
        sa.Text,
        nullable=False,
        server_default=sa.text("'staging'"),
    ),
    sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
    created_at(),
    updated_at(),
    # Crash-consistent finalize: a finalized object has exactly one finalize timestamp.
    sa.CheckConstraint("size_bytes >= 0", name="ck_blob_objects_size"),
    sa.CheckConstraint(
        "(state = 'finalized') = (finalized_at IS NOT NULL)",
        name="ck_blob_objects_finalized_timestamp",
    ),
    sa.CheckConstraint(
        "state IN ('staging', 'finalized', 'purged')",
        name="ck_blob_objects_state",
    ),
)

blob_references = sa.Table(
    "blob_references",
    METADATA,
    uuid_pk(),
    uuid_fk("blob_id", "blob_objects", ondelete="CASCADE"),
    # Polymorphic owner (same pattern as manifest items): referrer_kind names the table.
    sa.Column("referrer_kind", sa.Text, nullable=False),
    sa.Column("referrer_id", sa.Uuid(as_uuid=True), nullable=False),
    created_at(),
    sa.UniqueConstraint(
        "blob_id", "referrer_kind", "referrer_id",
        name="uq_blob_references_blob_referrer",
    ),
)

purge_tasks = sa.Table(
    "purge_tasks",
    METADATA,
    uuid_pk(),
    sa.Column("subject_kind", sa.Text, nullable=False),
    sa.Column("subject_id", sa.Uuid(as_uuid=True), nullable=False),
    uuid_fk("initiated_by_user_id", "users"),
    sa.Column(
        "status",
        sa.Text,
        nullable=False,
        server_default=sa.text("'pending'"),
    ),
    sa.Column("progress", JSONB, nullable=True),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    created_at(),
    updated_at(),
    sa.CheckConstraint(
        "finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at",
        name="ck_purge_tasks_order",
    ),
    sa.CheckConstraint(
        "status IN ('pending', 'running', 'completed', 'failed')",
        name="ck_purge_tasks_status",
    ),
)

audit_events = sa.Table(
    "audit_events",
    METADATA,
    uuid_pk(),
    uuid_fk("actor_user_id", "users", nullable=True, ondelete="SET NULL"),
    sa.Column("action", sa.Text, nullable=False),
    sa.Column("subject_kind", sa.Text, nullable=True),
    sa.Column("subject_id", sa.Uuid(as_uuid=True), nullable=True),
    sa.Column("details", JSONB, nullable=True),
    sa.Column("request_id", sa.Text, nullable=True),
    created_at(),
)

migration_metadata = sa.Table(
    "migration_metadata",
    METADATA,
    sa.Column("key", sa.Text, primary_key=True),
    sa.Column("value", sa.Text, nullable=False),
    sa.Column(
        "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
)
