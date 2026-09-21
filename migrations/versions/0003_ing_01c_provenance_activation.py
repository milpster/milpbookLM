"""
ING-01c provenance rows and activation-safe immutability.

Revision ID: 0003_ing_01c
Revises: 0002_ing_01b
"""

from alembic import op
from milpbooklm_adapters.db.schema import (
    APP_ROLE_GRANT_DDL,
    METADATA,
    TRIGGER_DDL,
    TRIGGER_FUNCTIONS,
    drop_triggers_sql,
)

revision = "0003_ing_01c"
down_revision = "0002_ing_01b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Converge fresh metadata and upgraded databases on provenance support."""
    bind = op.get_bind()
    # provenance_edges is the only table new in this revision. On a fresh
    # database 0001's live-metadata create_all already materialized it from
    # the same METADATA, so checkfirst is a no-op there; on an upgraded
    # database it creates the table from the live metadata (the single DDL
    # source of truth - raw ALTERs collide with fresh metadata, T13).
    METADATA.create_all(bind, checkfirst=True)
    # Re-apply every guard from the shared trigger definitions: the
    # immutability function now admits the canonical_documents
    # active/activated_at flip (the atomic active-document swap), and the new
    # provenance_edges table gets its immutable-endpoints trigger. The
    # drop-before-create form keeps interrupted upgrades restartable.
    for ddl in drop_triggers_sql():
        op.execute(ddl)
    for ddl in TRIGGER_FUNCTIONS:
        op.execute(ddl)
    for ddl in TRIGGER_DDL:
        op.execute(ddl)
    op.execute(APP_ROLE_GRANT_DDL)


def downgrade() -> None:
    """Remove the provenance table; guard re-application is forward-only in v1."""
    op.execute("DROP TABLE IF EXISTS provenance_edges")
