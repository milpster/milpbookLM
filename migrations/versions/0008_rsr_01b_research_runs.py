"""
RSR-01b: research run state machine columns (mode/budget/tools/approvals, step status/manifests).

Revision ID: 0008_rsr_01b
Revises: 0007_ing_02d

Extends the baseline ch05 research tables for the durable run state machine
(guide/11 Separation): explicit mode/budget/tools configuration per run, the
created/paused states, CAS revision, and per-step status + child input
manifest. Idempotent by construction (T13 lesson): a fresh database whose
0001 create_all already built the final live-metadata shape converges with a
genuine 0007 upgrade - every ALTER uses IF [NOT] EXISTS and each constraint
is dropped before being re-added.
"""

from alembic import op

revision = "0008_rsr_01b"
down_revision = "0007_ing_02d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the RSR-01b columns/checks idempotently."""
    op.execute(
        "ALTER TABLE research_runs ADD COLUMN IF NOT EXISTS mode TEXT"
        " NOT NULL DEFAULT 'source_discovery'"
    )
    op.execute(
        "ALTER TABLE research_runs ADD COLUMN IF NOT EXISTS budget JSONB NOT NULL DEFAULT '{}'"
    )
    op.execute(
        "ALTER TABLE research_runs ADD COLUMN IF NOT EXISTS tools JSONB NOT NULL DEFAULT '[]'"
    )
    op.execute(
        "ALTER TABLE research_runs ADD COLUMN IF NOT EXISTS approved_tools JSONB"
        " NOT NULL DEFAULT '[]'"
    )
    op.execute("ALTER TABLE research_runs ADD COLUMN IF NOT EXISTS error_code TEXT")
    op.execute(
        "ALTER TABLE research_runs ADD COLUMN IF NOT EXISTS revision INTEGER NOT NULL DEFAULT 0"
    )
    op.execute("ALTER TABLE research_runs ALTER COLUMN status SET DEFAULT 'created'")
    op.execute("ALTER TABLE research_runs DROP CONSTRAINT IF EXISTS ck_research_runs_status")
    op.execute(
        "ALTER TABLE research_runs ADD CONSTRAINT ck_research_runs_status "
        "CHECK (status IN ('created', 'running', 'paused', 'succeeded', 'failed', 'cancelled'))"
    )
    op.execute("ALTER TABLE research_runs DROP CONSTRAINT IF EXISTS ck_research_runs_mode")
    op.execute(
        "ALTER TABLE research_runs ADD CONSTRAINT ck_research_runs_mode "
        "CHECK (mode IN ('source_discovery', 'deep_research'))"
    )
    op.execute("ALTER TABLE research_run_steps ADD COLUMN IF NOT EXISTS tool_name TEXT")
    op.execute(
        "ALTER TABLE research_run_steps ADD COLUMN IF NOT EXISTS status TEXT"
        " NOT NULL DEFAULT 'pending'"
    )
    op.execute("ALTER TABLE research_run_steps ADD COLUMN IF NOT EXISTS input_manifest JSONB")
    op.execute("ALTER TABLE research_run_steps ADD COLUMN IF NOT EXISTS error_code TEXT")
    op.execute(
        "ALTER TABLE research_run_steps DROP CONSTRAINT IF EXISTS ck_research_run_steps_kind"
    )
    op.execute(
        "ALTER TABLE research_run_steps ADD CONSTRAINT ck_research_run_steps_kind "
        "CHECK (step_kind IN ('search', 'fetch', 'browser', 'evaluate', 'plan', 'synthesize', "
        "'generate', 'import', 'retrieve'))"
    )
    op.execute(
        "ALTER TABLE research_run_steps DROP CONSTRAINT IF EXISTS ck_research_run_steps_status"
    )
    op.execute(
        "ALTER TABLE research_run_steps ADD CONSTRAINT ck_research_run_steps_status "
        "CHECK (status IN ('pending', 'running', 'succeeded', 'failed', 'skipped'))"
    )


def downgrade() -> None:
    """Keep the columns (research runs depend on them); relax nothing."""
