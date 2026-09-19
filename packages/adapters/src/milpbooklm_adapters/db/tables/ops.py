"""
Operations tables: jobs, job attempts, outbox events, idempotency keys (ch05, TAD-005).

PostgreSQL leases/outbox implement jobs and events. Outbox events commit in the same
transaction as the aggregate they describe (TECH-05-001) - no cross-transaction coupling.
Idempotency keys use a plain unique (scope, key): concurrent duplicate inserts lose at the
constraint, and the idempotency section (concurrency.py) turns that race into a read.
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

jobs = sa.Table(
    "jobs",
    METADATA,
    uuid_pk(),
    sa.Column("queue", sa.Text, nullable=False),
    sa.Column("kind", sa.Text, nullable=False),
    sa.Column("payload", JSONB, nullable=False),
    sa.Column(
        "status",
        sa.Text,
        nullable=False,
        server_default=sa.text("'queued'"),
    ),
    sa.Column("lease_owner", sa.Text, nullable=True),
    sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("attempts", sa.Integer, nullable=False, server_default=sa.text("0")),
    sa.Column("max_attempts", sa.Integer, nullable=False, server_default=sa.text("3")),
    uuid_fk("idempotency_key_id", "idempotency_keys", nullable=True, ondelete="SET NULL"),
    uuid_fk("requested_by_user_id", "users", nullable=True, ondelete="SET NULL"),
    sa.Column("subject_kind", sa.Text, nullable=True),
    sa.Column("subject_id", sa.Uuid(as_uuid=True), nullable=True),
    revision_column(),
    etag_column(),
    sa.Column(
        "enqueued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    created_at(),
    updated_at(),
    # A lease is only meaningful while leased: the invariant is checkable in one row.
    sa.Index("ix_jobs_queue_status", "queue", "status"),
    sa.CheckConstraint(
        "lease_owner IS NULL OR status IN ('leased', 'running')",
        name="ck_jobs_lease_consistency",
    ),
    sa.CheckConstraint("attempts >= 0", name="ck_jobs_attempts_non_negative"),
    sa.CheckConstraint("max_attempts > 0", name="ck_jobs_max_attempts_positive"),
    sa.CheckConstraint(
        "status IN ('queued', 'leased', 'running', 'succeeded', 'failed', 'cancelled')",
        name="ck_jobs_status",
    ),
)

job_attempts = sa.Table(
    "job_attempts",
    METADATA,
    uuid_pk(),
    uuid_fk("job_id", "jobs", ondelete="CASCADE"),
    sa.Column("attempt_number", sa.Integer, nullable=False),
    sa.Column("worker_id", sa.Text, nullable=True),
    sa.Column(
        "outcome",
        sa.Text,
        nullable=False,
        server_default=sa.text("'running'"),
    ),
    sa.Column("error", JSONB, nullable=True),
    sa.Column(
        "started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
    sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    created_at(),
    sa.UniqueConstraint("job_id", "attempt_number", name="uq_job_attempts_job_number"),
    sa.CheckConstraint("attempt_number > 0", name="ck_job_attempts_number"),
    sa.CheckConstraint(
        "outcome IN ('running', 'succeeded', 'failed', 'timeout', 'cancelled')",
        name="ck_job_attempts_outcome",
    ),
)

outbox_events = sa.Table(
    "outbox_events",
    METADATA,
    uuid_pk(),
    sa.Column("seq", sa.BigInteger, sa.Identity(always=True), nullable=False, unique=True),
    sa.Column("aggregate_kind", sa.Text, nullable=False),
    sa.Column("aggregate_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("event_type", sa.Text, nullable=False),
    sa.Column("payload", JSONB, nullable=False),
    sa.Column("dispatched", sa.Boolean, nullable=False, server_default=sa.text("false")),
    sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
    created_at(),
    sa.Index("ix_outbox_events_pending", "dispatched", "created_at"),
    sa.CheckConstraint(
        "dispatched_at IS NULL OR (dispatched = true AND dispatched_at >= created_at)",
        name="ck_outbox_events_dispatched",
    ),
)

idempotency_keys = sa.Table(
    "idempotency_keys",
    METADATA,
    uuid_pk(),
    sa.Column("scope", sa.Text, nullable=False),
    sa.Column("key", sa.Text, nullable=False),
    sa.Column("request_hash", sa.Text, nullable=False),
    sa.Column("response_hash", sa.Text, nullable=True),
    sa.Column(
        "status",
        sa.Text,
        nullable=False,
        server_default=sa.text("'in_flight'"),
    ),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    created_at(),
    # The uniqueness is the concurrency protection: two sessions cannot both create the
    # same (scope, key) - the loser gets a unique violation and reads the winner.
    sa.UniqueConstraint("scope", "key", name="uq_idempotency_keys_scope_key"),
    sa.CheckConstraint("expires_at > created_at", name="ck_idempotency_keys_expiry"),
    sa.CheckConstraint("status IN ('in_flight', 'completed')", name="ck_idempotency_keys_status"),
)
