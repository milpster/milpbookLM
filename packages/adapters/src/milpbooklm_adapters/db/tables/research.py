"""
Research run tables: research_runs, run_steps, evidence snapshots (ch05 §10).

Run evidence is private to the initiating run/user by default (ARCH-05-018..020):
* visibility defaults to private and only admits 'notebook_shared' after explicit sharing;
* a snapshot exposed by a shared artifact needs a defined retention/share policy
  (retention_policy column, checked by the domain layer before publication);
* snapshots are immutable once captured (trigger) and may be promoted to a SourceVersion
  (promoted_source_version_id is the single updatable field).
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from ._common import METADATA, created_at, updated_at, uuid_fk, uuid_pk

research_runs = sa.Table(
    "research_runs",
    METADATA,
    uuid_pk(),
    uuid_fk("notebook_id", "notebooks", ondelete="CASCADE"),
    uuid_fk("initiated_by_user_id", "users"),
    sa.Column(
        "visibility",
        sa.Text,
        nullable=False,
        server_default=sa.text("'private'"),
    ),
    sa.Column("goal", sa.Text, nullable=False),
    sa.Column("plan", JSONB, nullable=True),
    sa.Column(
        "status",
        sa.Text,
        nullable=False,
        server_default=sa.text("'running'"),
    ),
    # Immutable initial run snapshot + append-only ledger (steps below); a final report
    # never cites unversioned mutable run state (ARCH-05-015).
    sa.Column("initial_run_snapshot", JSONB, nullable=True),
    sa.Column("cost_usage", JSONB, nullable=True),
    uuid_fk("report_artifact_version_id", "artifact_versions", nullable=True, ondelete="SET NULL"),
    sa.Column("candidate_imports", JSONB, nullable=True),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    created_at(),
    updated_at(),
    sa.CheckConstraint(
        "status IN ('running', 'succeeded', 'failed', 'cancelled')",
        name="ck_research_runs_status",
    ),
    sa.CheckConstraint(
        "visibility IN ('private', 'notebook_shared')",
        name="ck_research_runs_visibility",
    ),
)

research_run_steps = sa.Table(
    "research_run_steps",
    METADATA,
    uuid_pk(),
    uuid_fk("run_id", "research_runs", ondelete="CASCADE"),
    sa.Column("step_number", sa.Integer, nullable=False),
    sa.Column(
        "step_kind",
        sa.Text,
        nullable=False,
    ),
    sa.Column("tool_result", JSONB, nullable=True),
    uuid_fk(
        "evidence_snapshot_id", "research_evidence_snapshots", nullable=True, ondelete="SET NULL"
    ),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    created_at(),
    sa.UniqueConstraint("run_id", "step_number", name="uq_research_run_steps_run_number"),
    sa.CheckConstraint("step_number > 0", name="ck_research_run_steps_number"),
    sa.CheckConstraint(
        "step_kind IN ('search', 'fetch', 'evaluate', 'plan', 'synthesize', 'generate')",
        name="ck_research_run_steps_kind",
    ),
)

research_evidence_snapshots = sa.Table(
    "research_evidence_snapshots",
    METADATA,
    uuid_pk(),
    uuid_fk("run_id", "research_runs", ondelete="CASCADE"),
    sa.Column("origin_tool", sa.Text, nullable=True),
    sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
    # Final URL or other origin locator where applicable.
    sa.Column("origin_locator", sa.Text, nullable=True),
    sa.Column("content_sha256", sa.Text, nullable=False),
    uuid_fk("blob_id", "blob_objects", nullable=True, ondelete="SET NULL"),
    sa.Column("locators", JSONB, nullable=True),
    sa.Column("access_metadata", JSONB, nullable=True),
    # Required before a shared artifact may expose this snapshot (ARCH-05-018/020).
    sa.Column("retention_policy", JSONB, nullable=True),
    # Set once when the evidence is promoted to a normal SourceVersion (ARCH-05-018).
    uuid_fk("promoted_source_version_id", "source_versions", nullable=True, ondelete="SET NULL"),
    created_at(),
)
