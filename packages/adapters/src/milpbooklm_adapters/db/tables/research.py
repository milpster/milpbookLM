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

from ._common import METADATA, created_at, revision_column, updated_at, uuid_fk, uuid_pk

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
    # RSR-01b: explicit mode/budget/tools configuration per run (27.1).
    sa.Column(
        "mode",
        sa.Text,
        nullable=False,
        server_default=sa.text("'source_discovery'"),
    ),
    sa.Column("budget", JSONB, nullable=False, server_default=sa.text("'{}'")),
    sa.Column("tools", JSONB, nullable=False, server_default=sa.text("'[]'")),
    sa.Column("approved_tools", JSONB, nullable=False, server_default=sa.text("'[]'")),
    sa.Column(
        "status",
        sa.Text,
        nullable=False,
        server_default=sa.text("'created'"),
    ),
    # Immutable initial run snapshot + append-only ledger (steps below); a final report
    # never cites unversioned mutable run state (ARCH-05-015).
    sa.Column("initial_run_snapshot", JSONB, nullable=True),
    sa.Column("cost_usage", JSONB, nullable=True),
    uuid_fk("report_artifact_version_id", "artifact_versions", nullable=True, ondelete="SET NULL"),
    sa.Column("candidate_imports", JSONB, nullable=True),
    sa.Column("error_code", sa.Text, nullable=True),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    revision_column(),
    created_at(),
    updated_at(),
    sa.CheckConstraint(
        "status IN ('created', 'running', 'paused', 'succeeded', 'failed', 'cancelled')",
        name="ck_research_runs_status",
    ),
    sa.CheckConstraint(
        "visibility IN ('private', 'notebook_shared')",
        name="ck_research_runs_visibility",
    ),
    sa.CheckConstraint(
        "mode IN ('source_discovery', 'deep_research')",
        name="ck_research_runs_mode",
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
    sa.Column("tool_name", sa.Text, nullable=True),
    sa.Column(
        "status",
        sa.Text,
        nullable=False,
        server_default=sa.text("'pending'"),
    ),
    # Child input manifest recorded by every planning/model step (ARCH-11-001).
    sa.Column("input_manifest", JSONB, nullable=True),
    sa.Column("tool_result", JSONB, nullable=True),
    sa.Column("error_code", sa.Text, nullable=True),
    uuid_fk(
        "evidence_snapshot_id", "research_evidence_snapshots", nullable=True, ondelete="SET NULL"
    ),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    created_at(),
    sa.UniqueConstraint("run_id", "step_number", name="uq_research_run_steps_run_number"),
    sa.CheckConstraint("step_number > 0", name="ck_research_run_steps_number"),
    sa.CheckConstraint(
        "step_kind IN ('search', 'fetch', 'browser', 'evaluate', 'plan', 'synthesize', "
        "'generate', 'import', 'retrieve')",
        name="ck_research_run_steps_kind",
    ),
    sa.CheckConstraint(
        "status IN ('pending', 'running', 'succeeded', 'failed', 'skipped')",
        name="ck_research_run_steps_status",
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
