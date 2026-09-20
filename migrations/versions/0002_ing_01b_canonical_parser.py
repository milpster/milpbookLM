"""
ING-01b parser outcomes and canonical contract persistence.

Revision ID: 0002_ing_01b
Revises: 0001_baseline
Create Date: 2026-09-21
"""

from alembic import op

revision = "0002_ing_01b"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

_NODE_KINDS = (
    "document", "section", "paragraph", "heading", "list", "list_item", "quote", "code",
    "table", "row", "cell", "image", "figure", "caption", "page", "slide", "sheet",
    "transcript_segment", "speaker_turn", "attachment", "reference", "generic",
)


def upgrade() -> None:
    """Add explicit parser states and immutable canonical result metadata."""
    op.execute("ALTER TABLE source_versions DROP CONSTRAINT ck_source_versions_status")
    op.execute("ALTER TABLE source_versions ADD COLUMN parse_error_code text")
    op.execute(
        "ALTER TABLE source_versions ADD CONSTRAINT ck_source_versions_status CHECK "
        "(status IN ('activating','parsing','parsed','encrypted','parse_failed',"
        "'active','inactive','tombstoned'))"
    )
    op.execute(
        "ALTER TABLE source_versions ADD CONSTRAINT ck_source_versions_parse_error CHECK "
        "((status IN ('encrypted','parse_failed')) = (parse_error_code IS NOT NULL))"
    )
    for ddl in (
        "ADD COLUMN parser_identity text NOT NULL DEFAULT 'legacy'",
        "ADD COLUMN parser_profile text NOT NULL DEFAULT 'legacy'",
        "ADD COLUMN tool_versions jsonb NOT NULL DEFAULT '[]'::jsonb",
        "ADD COLUMN contract_json jsonb NOT NULL DEFAULT '{}'::jsonb",
    ):
        op.execute(f"ALTER TABLE canonical_documents {ddl}")
    for ddl in (
        "ADD COLUMN structural_identity text NOT NULL DEFAULT 'legacy'",
        "ADD COLUMN authority_class text NOT NULL DEFAULT 'source_authored'",
        "ADD COLUMN language text",
    ):
        op.execute(f"ALTER TABLE canonical_nodes {ddl}")
    op.execute("ALTER TABLE canonical_nodes DROP CONSTRAINT ck_canonical_nodes_type")
    quoted = ",".join(f"'{kind}'" for kind in _NODE_KINDS)
    op.execute(
        "ALTER TABLE canonical_nodes ADD CONSTRAINT ck_canonical_nodes_type "
        f"CHECK (node_type IN ({quoted}))"
    )
    op.execute(
        "ALTER TABLE canonical_locators ADD COLUMN structural_path jsonb "
        "NOT NULL DEFAULT '[]'::jsonb"
    )


def downgrade() -> None:
    """Remove ING-01b fields after restoring baseline-compatible values."""
    op.execute("DELETE FROM canonical_documents WHERE parser_identity <> 'legacy'")
    op.execute("ALTER TABLE canonical_locators DROP COLUMN structural_path")
    op.execute("ALTER TABLE canonical_nodes DROP CONSTRAINT ck_canonical_nodes_type")
    op.execute(
        "ALTER TABLE canonical_nodes ADD CONSTRAINT ck_canonical_nodes_type CHECK "
        "(node_type IN ('heading','paragraph','list','list_item','table','image',"
        "'page','slide','sheet'))"
    )
    for column in ("language", "authority_class", "structural_identity"):
        op.execute(f"ALTER TABLE canonical_nodes DROP COLUMN {column}")
    for column in ("contract_json", "tool_versions", "parser_profile", "parser_identity"):
        op.execute(f"ALTER TABLE canonical_documents DROP COLUMN {column}")
    op.execute("UPDATE source_versions SET status = 'activating', parse_error_code = NULL")
    op.execute("ALTER TABLE source_versions DROP CONSTRAINT ck_source_versions_parse_error")
    op.execute("ALTER TABLE source_versions DROP CONSTRAINT ck_source_versions_status")
    op.execute("ALTER TABLE source_versions DROP COLUMN parse_error_code")
    op.execute(
        "ALTER TABLE source_versions ADD CONSTRAINT ck_source_versions_status CHECK "
        "(status IN ('activating','active','inactive','tombstoned'))"
    )
