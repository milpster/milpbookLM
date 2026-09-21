"""
Knowledge-index tables (IDX-01, ch08): index generations and chunk rows.

Index rows are derived state, logically grouped by the immutable
``index_generation_id``. Every row carries the full discriminator set the
retrieval SQL and audits rely on: notebook, source, source-version, canonical
node/span, language, chunker revision, token count, text checksum and the
effective-restriction discriminator. A generation becomes ``ready`` atomically
(atomic swap: this generation ready, the prior ready one superseded) and rows
are queryable only through retrieval that constrains active source versions.
Removal filters rows immediately (query-level); purge deletes them.

The ``embedding`` column is pgvector ``vector(1024)`` (D14: bge-m3, 1024-dim).
The Python type is rendered by DDL only - no pgvector Python package is used;
values cross as text with an explicit ``::vector`` cast (raw-SQL boundary).
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR

from ._common import METADATA, created_at, uuid_fk, uuid_pk

DEFAULT_EMBEDDING_DIMENSION = 1024


class VectorType(sa.types.UserDefinedType[Any]):
    """pgvector ``vector(n)`` column: DDL rendering only (no Python-side binding)."""

    cache_ok = True

    def __init__(self, dimension: int = DEFAULT_EMBEDDING_DIMENSION) -> None:
        """Bind the vector dimension (rendered into the DDL)."""
        super().__init__()
        self.dimension = dimension

    def get_col_spec(self, **kw: Any) -> str:
        """Render the column type for DDL."""
        return f"vector({self.dimension})"


index_generations = sa.Table(
    "index_generations",
    METADATA,
    uuid_pk(),
    uuid_fk("notebook_id", "notebooks", ondelete="CASCADE"),
    uuid_fk("source_id", "sources", ondelete="CASCADE"),
    uuid_fk("source_version_id", "source_versions", ondelete="CASCADE"),
    sa.Column("chunker_profile", sa.Text, nullable=False),
    sa.Column("chunker_revision", sa.Text, nullable=False),
    sa.Column("embedding_model", sa.Text, nullable=False),
    sa.Column("embedding_model_ref", sa.Text, nullable=True),
    sa.Column("embedding_dimension", sa.Integer, nullable=False),
    sa.Column("embedding_normalization", sa.Text, nullable=False),
    sa.Column("fusion_config_version", sa.Text, nullable=False),
    sa.Column("reranker_config_version", sa.Text, nullable=True),
    sa.Column(
        "status",
        sa.Text,
        nullable=False,
        server_default=sa.text("'building'"),
        # ch08 lifecycle: absent, building, ready, stale, failed (+ superseded swap state).
    ),
    sa.Column("manifest", JSONB, nullable=False),
    sa.Column("error_code", sa.Text, nullable=True),
    sa.Column("chunk_count", sa.Integer, nullable=False, server_default=sa.text("0")),
    created_at(),
    sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint(
        "status IN ('building', 'ready', 'superseded', 'stale', 'failed')",
        name="ck_index_generations_status",
    ),
    sa.CheckConstraint("embedding_dimension > 0", name="ck_index_generations_dimension"),
    # Atomic swap target: at most one ready generation per source version.
    sa.Index(
        "uq_index_generations_one_ready",
        "source_version_id",
        unique=True,
        postgresql_where=sa.text("status = 'ready'"),
    ),
)

index_chunks = sa.Table(
    "index_chunks",
    METADATA,
    # Chunk IDs are deterministic per node + chunker profile, so they repeat
    # across generations of a version; the composite PK scopes them.
    sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
    uuid_fk("index_generation_id", "index_generations", ondelete="CASCADE"),
    # Full discriminator columns (ch08): retrieval constrains on these in SQL.
    uuid_fk("notebook_id", "notebooks", ondelete="CASCADE"),
    uuid_fk("source_id", "sources", ondelete="CASCADE"),
    uuid_fk("source_version_id", "source_versions", ondelete="CASCADE"),
    uuid_fk("canonical_document_id", "canonical_documents", ondelete="CASCADE"),
    uuid_fk("canonical_node_id", "canonical_nodes", ondelete="CASCADE"),
    sa.Column("char_start", sa.Integer, nullable=False),
    sa.Column("char_end", sa.Integer, nullable=False),
    sa.Column("language", sa.Text, nullable=False),
    sa.Column("chunker_revision", sa.Text, nullable=False),
    sa.Column("token_count", sa.Integer, nullable=False),
    sa.Column("text_checksum", sa.Text, nullable=False),
    sa.Column("text", sa.Text, nullable=False),
    sa.Column("fts_config", sa.Text, nullable=False),
    # Per-row tsvector (config varies by language: english/german/simple fallback).
    sa.Column("fts_vector", TSVECTOR, nullable=False),
    sa.Column("restriction_discriminator", sa.Text, nullable=True),
    sa.Column("section_ancestry", JSONB, nullable=False),
    sa.Column("node_spans", JSONB, nullable=False),
    # Links reference chunk ids inside the same generation; the chunker
    # enforces them (foreign keys need a unique target, which id no longer is).
    sa.Column("prev_chunk_id", sa.Uuid(as_uuid=True), nullable=True),
    sa.Column("next_chunk_id", sa.Uuid(as_uuid=True), nullable=True),
    sa.Column("embedding", VectorType(DEFAULT_EMBEDDING_DIMENSION), nullable=True),
    created_at(),
    sa.PrimaryKeyConstraint("index_generation_id", "id", name="index_chunks_pkey"),
    sa.CheckConstraint("char_end >= char_start", name="ck_index_chunks_span"),
    sa.CheckConstraint("token_count >= 0", name="ck_index_chunks_tokens"),
    sa.Index("idx_index_chunks_generation", "index_generation_id"),
    # GIN for FTS (ch08: GIN indexes for full-text search).
    sa.Index("idx_index_chunks_fts", "fts_vector", postgresql_using="gin"),
)
