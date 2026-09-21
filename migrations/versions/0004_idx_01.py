"""
IDX-01 knowledge-index tables: generations, chunk rows, GIN FTS index, pgvector.

Revision ID: 0004_idx_01
Revises: 0003_ing_01c

The pgvector extension (REFERENCE-DEPENDENCIES: "PostgreSQL 18 plus pgvector")
is created here. ``CREATE EXTENSION IF NOT EXISTS`` works when the migration
role may create extensions (database owner / superuser); on installations
where the migration role cannot, a DBA pre-creates the extension and this
statement is a no-op. The index tables come from the live shared METADATA
(create_all, checkfirst) so fresh and upgraded databases converge (T13/T14
pattern); the trigger set is re-applied drop-before-create so interrupted
upgrades stay restartable, and the app role receives DML on the new objects.
"""

from alembic import op
from milpbooklm_adapters.db.schema import (
    APP_ROLE_GRANT_DDL,
    METADATA,
    TRIGGER_DDL,
    TRIGGER_FUNCTIONS,
    drop_triggers_sql,
)

revision = "0004_idx_01"
down_revision = "0003_ing_01c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Converge fresh metadata and upgraded databases on index support."""
    bind = op.get_bind()
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    METADATA.create_all(bind, checkfirst=True)
    for ddl in drop_triggers_sql():
        op.execute(ddl)
    for ddl in TRIGGER_FUNCTIONS:
        op.execute(ddl)
    for ddl in TRIGGER_DDL:
        op.execute(ddl)
    op.execute(APP_ROLE_GRANT_DDL)


def downgrade() -> None:
    """Remove the index tables; extension removal is forward-only in v1."""
    op.execute("DROP TABLE IF EXISTS index_chunks")
    op.execute("DROP TABLE IF EXISTS index_generations")
