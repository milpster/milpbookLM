"""Permit explicit AD-016 purge transactions through immutable-row guards."""

from alembic import op
from milpbooklm_adapters.db.triggers import TRIGGER_FUNCTIONS

revision = "0007_ing_02d"
down_revision = "0006_rag_01b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Install purge-aware trigger functions without weakening ordinary writes."""
    for statement in TRIGGER_FUNCTIONS:
        op.execute(statement)


def downgrade() -> None:
    """Keep guards installed because older revisions require immutability."""
