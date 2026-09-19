"""
FND-03 baseline: all ch05 tables with uuidv7 defaults, invariants, immutability triggers.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-09-18

The DDL source of truth is milpbooklm_adapters.db.schema.METADATA (shared with the
schema-completeness tests); this revision is deliberately thin so migration and test
assertions cannot drift apart. create_all(checkfirst=True) makes the upgrade
restartable: re-running after an interruption is a no-op.
"""

from alembic import op
from milpbooklm_adapters.db.schema import (
    APP_ROLE_GRANT_DDL,
    METADATA,
    TRIGGER_DDL,
    TRIGGER_FUNCTIONS,
    drop_triggers_sql,
)

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create every ch05 table, immutability trigger and app-role DML grant."""
    bind = op.get_bind()
    # The pgvector extension is a superuser bootstrap-time action (migrations/roles.sql),
    # NOT created here: pgvector is not a trusted extension and the migration role is not a
    # superuser. The schema below assumes it already exists (readiness checks it too).
    METADATA.create_all(bind, checkfirst=True)
    for ddl in TRIGGER_FUNCTIONS:
        op.execute(ddl)
    for ddl in TRIGGER_DDL:
        op.execute(ddl)
    op.execute(APP_ROLE_GRANT_DDL)


def downgrade() -> None:
    """Drop every table CASCADE (FK cycles) and remove the guard functions."""
    # Destructive baseline rollback. The schema has deliberate bidirectional FK cycles
    # (sources<->source_versions, notes<->note_revisions, artifacts<->artifact_versions);
    # a plain drop_all cannot topologically sort a cycle, so drop each table CASCADE to
    # break the dependent constraints. The guard functions are dropped afterwards (their
    # triggers already vanish with the tables).
    for table in reversed(list(METADATA.tables.values())):
        op.execute(f"DROP TABLE IF EXISTS {table.name} CASCADE")
    for ddl in drop_triggers_sql():
        op.execute(ddl)
