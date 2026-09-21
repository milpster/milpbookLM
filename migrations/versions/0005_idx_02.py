"""
IDX-01 chunk primary key: scope the chunk id to its generation.

Revision ID: 0005_idx_02
Revises: 0004_idx_01

Chunk ids are deterministic per node + chunker profile, so a rebuild
generation reuses the same ids; id alone cannot be the primary key.
Uniqueness becomes per generation: (index_generation_id, id). The prev/next
links point at chunk ids inside one generation and are enforced by the
chunker, not by foreign keys (a foreign key needs a unique target).
"""

from alembic import op

revision = "0005_idx_02"
down_revision = "0004_idx_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Scope the chunk primary key to its generation."""
    op.drop_constraint("uq_index_chunks_generation_chunk", "index_chunks", type_="unique")
    op.drop_constraint("index_chunks_prev_chunk_id_fkey", "index_chunks", type_="foreignkey")
    op.drop_constraint("index_chunks_next_chunk_id_fkey", "index_chunks", type_="foreignkey")
    op.drop_constraint("index_chunks_pkey", "index_chunks", type_="primary")
    op.create_primary_key("index_chunks_pkey", "index_chunks", ["index_generation_id", "id"])


def downgrade() -> None:
    """Restore the id-only key; chunk rows must be rebuilt afterwards."""
    op.execute("DELETE FROM index_chunks")
    op.drop_constraint("index_chunks_pkey", "index_chunks", type_="primary")
    op.create_primary_key("index_chunks_pkey", "index_chunks", ["id"])
    op.create_unique_constraint(
        "uq_index_chunks_generation_chunk", "index_chunks", ["index_generation_id", "id"]
    )
    op.create_foreign_key(
        "index_chunks_prev_chunk_id_fkey",
        "index_chunks",
        "index_chunks",
        ["prev_chunk_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "index_chunks_next_chunk_id_fkey",
        "index_chunks",
        "index_chunks",
        ["next_chunk_id"],
        ["id"],
        ondelete="SET NULL",
    )
