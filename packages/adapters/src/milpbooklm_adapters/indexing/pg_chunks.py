"""
Chunk-row persistence and canonical-document reads (IDX-01, ch08).

Chunk rows are idempotent under re-insertion (unique generation + chunk id),
which makes the build resumable after lease recovery. The per-row tsvector is
computed in SQL from the chunk's language-specific config (english/german with
an explicit ``simple`` fallback) - the ranking stays native PostgreSQL FTS and
is intentionally never labeled BM25. The effective-restriction discriminator
(all-users restriction rows + source policy) is computed once per build and
stamped on every row.
"""

from __future__ import annotations

import hashlib
import json
import uuid

import sqlalchemy as sa
from milpbooklm_contracts.canonical_document import CanonicalDocument
from milpbooklm_domain.indexing import Chunk, fts_config_for_language

from milpbooklm_adapters.db.tables.indexing import index_chunks, index_generations
from milpbooklm_adapters.db.tables.sources import (
    canonical_documents,
    source_restrictions,
    source_versions,
    sources,
)


class PgChunkStore:
    """Chunk rows under a generation (lexical columns + vector updates)."""

    def __init__(self, engine: sa.engine.Engine) -> None:
        """Bind the application-role engine."""
        self._engine = engine

    def existing_chunk_ids(self, generation_id: uuid.UUID) -> frozenset[uuid.UUID]:
        """Return the chunk IDs already persisted for the generation (resume check)."""
        with self._engine.begin() as connection:
            rows = connection.execute(
                sa.select(index_chunks.c.id).where(
                    index_chunks.c.index_generation_id == generation_id
                )
            ).all()
        return frozenset(row[0] for row in rows)

    def insert_chunks(
        self, generation_id: uuid.UUID, document: CanonicalDocument, chunks: tuple[Chunk, ...]
    ) -> int:
        """Persist chunk rows (lexical); skip IDs already present; return inserted count."""
        if not chunks:
            return 0
        with self._engine.begin() as connection:
            generation = connection.execute(
                sa.select(
                    index_generations.c.notebook_id,
                    index_generations.c.source_id,
                    index_generations.c.source_version_id,
                ).where(index_generations.c.id == generation_id)
            ).mappings().one()
            discriminator = self._restriction_discriminator(
                connection, generation["source_version_id"]
            )
            inserted = 0
            for chunk in chunks:
                fts_config = fts_config_for_language(chunk.language)
                result = connection.execute(
                    sa.text(
                        """
                        INSERT INTO index_chunks (
                          id, index_generation_id, notebook_id, source_id,
                          source_version_id, canonical_document_id, canonical_node_id,
                          char_start, char_end, language, chunker_revision, token_count,
                          text_checksum, text, fts_config, fts_vector,
                          restriction_discriminator, section_ancestry, node_spans,
                          prev_chunk_id, next_chunk_id
                        ) VALUES (
                          :id, :generation_id, :notebook_id, :source_id,
                          :source_version_id, :document_id, :node_id,
                          :char_start, :char_end, :language, :chunker_revision, :token_count,
                          :text_checksum, :text, :fts_config,
                          to_tsvector(CAST(:fts_config_rc AS regconfig), :text),
                          :discriminator, :section_ancestry, :node_spans,
                          :prev_chunk_id, :next_chunk_id
                        )
                        ON CONFLICT (index_generation_id, id) DO NOTHING
                        """
                    ),
                    {
                        "id": chunk.chunk_id,
                        "generation_id": generation_id,
                        "notebook_id": generation["notebook_id"],
                        "source_id": generation["source_id"],
                        "source_version_id": generation["source_version_id"],
                        "document_id": document.document_id,
                        "node_id": chunk.node_id,
                        "char_start": chunk.char_start,
                        "char_end": chunk.char_end,
                        "language": chunk.language,
                        "chunker_revision": self._chunker_revision(connection, generation_id),
                        "token_count": chunk.token_count,
                        "text_checksum": chunk.text_checksum,
                        "text": chunk.text,
                        "fts_config": fts_config,
                        "fts_config_rc": fts_config,
                        "discriminator": discriminator,
                        "section_ancestry": json.dumps(
                            [str(node_id) for node_id in chunk.section_ancestry]
                        ),
                        "node_spans": json.dumps(
                            [
                                {
                                    "node_id": str(span.node_id),
                                    "char_start": span.char_start,
                                    "char_end": span.char_end,
                                }
                                for span in chunk.node_spans
                            ]
                        ),
                        "prev_chunk_id": chunk.prev_chunk_id,
                        "next_chunk_id": chunk.next_chunk_id,
                    },
                )
                inserted += result.rowcount
        return inserted

    def set_embedding(
        self, generation_id: uuid.UUID, chunk_id: uuid.UUID, vector_text: str
    ) -> None:
        """Attach one vector (text form, explicit cast) to a generation's chunk row."""
        with self._engine.begin() as connection:
            connection.execute(
                sa.text(
                    "UPDATE index_chunks SET embedding = CAST(:vector AS vector) "
                    "WHERE id = :id AND index_generation_id = :generation_id"
                ),
                {
                    "vector": vector_text,
                    "id": chunk_id,
                    "generation_id": generation_id,
                },
            )

    @staticmethod
    def _chunker_revision(
        connection: sa.engine.Connection, generation_id: uuid.UUID
    ) -> str:
        row = connection.execute(
            sa.select(index_generations.c.chunker_revision).where(
                index_generations.c.id == generation_id
            )
        ).first()
        return str(row[0]) if row is not None else ""

    @staticmethod
    def _restriction_discriminator(
        connection: sa.engine.Connection, source_version_id: uuid.UUID
    ) -> str:
        """Stamp: sha256 over all-users restrictions + source policy (prototype scope)."""
        rows = connection.execute(
            sa.select(source_restrictions.c.restriction_type).where(
                source_restrictions.c.source_version_id == source_version_id,
                source_restrictions.c.user_id.is_(None),
            )
        ).all()
        policy_row = connection.execute(
            sa.select(sources.c.restriction_policy)
            .join(source_versions, source_versions.c.id == sources.c.current_version_id)
            .where(source_versions.c.id == source_version_id)
        ).first()
        policy = policy_row[0] if policy_row is not None else None
        canonical = json.dumps(
            {"all_users": sorted(row[0] for row in rows), "policy": policy},
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class CanonicalDocumentMissingError(LookupError):
    """The canonical document row is absent."""


class PgCanonicalDocumentReader:
    """Loads a persisted canonical document (the chunking input)."""

    def __init__(self, engine: sa.engine.Engine) -> None:
        """Bind the application-role engine."""
        self._engine = engine

    def load(self, document_id: uuid.UUID) -> CanonicalDocument:
        """Load the document contract; raise when absent."""
        with self._engine.begin() as connection:
            row = connection.execute(
                sa.select(canonical_documents.c.contract_json).where(
                    canonical_documents.c.id == document_id
                )
            ).first()
        if row is None:
            raise CanonicalDocumentMissingError(str(document_id))
        return CanonicalDocument.from_json(row[0])
