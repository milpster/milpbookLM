"""Add per-conversation chat configuration and instructions."""

from alembic import op

revision = "0006_rag_01b"
down_revision = "0005_idx_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add chat columns for databases created before the task-17 metadata revision."""
    op.execute(
        "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS chat_config jsonb "
        "NOT NULL DEFAULT '{}'::jsonb"
    )
    op.execute(
        "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS instructions text NOT NULL DEFAULT ''"
    )


def downgrade() -> None:
    """Remove task-17 columns when rolling back this idempotent migration."""
    op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS instructions")
    op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS chat_config")
