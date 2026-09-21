"""
Index-generation lifecycle persistence (IDX-01, ch08).

States follow the guide's index lifecycle: ``building`` -> ``ready`` (atomic
swap) -> ``superseded`` (rebuild swap), with ``failed``/``stale`` for explicit
outcomes. The swap is ONE transaction: the prior ready generation of the same
source version is superseded and the new one is made ready, so retrieval never
sees two ready generations (partial unique index ``uq_index_generations_one_ready``).
Purge deletes a source's generations (chunk rows cascade); removal filters
rows at query level and is handled by the retrieval SQL, not here.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from milpbooklm_application.indexing import GenerationIdentity, IndexBuildConfig
from sqlalchemy.dialects.postgresql import insert as pg_insert

from milpbooklm_adapters.db.tables.indexing import index_generations


class PgGenerationStore:
    """Generation rows over the app-role engine."""

    def __init__(self, engine: sa.engine.Engine) -> None:
        """Bind the application-role engine."""
        self._engine = engine

    def get_status(self, generation_id: uuid.UUID) -> str | None:
        """Return the generation status (None when absent)."""
        with self._engine.begin() as connection:
            row = connection.execute(
                sa.select(index_generations.c.status).where(
                    index_generations.c.id == generation_id
                )
            ).first()
        return None if row is None else str(row[0])

    def create(self, identity: GenerationIdentity, config: IndexBuildConfig) -> None:
        """Create the generation row with its immutable manifest (idempotent)."""
        with self._engine.begin() as connection:
            connection.execute(
                pg_insert(index_generations)
                .values(
                    id=identity.generation_id,
                    notebook_id=identity.notebook_id,
                    source_id=identity.source_id,
                    source_version_id=identity.source_version_id,
                    chunker_profile=config.profile.name,
                    chunker_revision=config.profile.revision,
                    embedding_model=config.embedding.model,
                    embedding_model_ref=config.embedding.model_ref,
                    embedding_dimension=config.embedding.dimension,
                    embedding_normalization=config.embedding.normalization,
                    fusion_config_version=config.fusion_config_version,
                    reranker_config_version=config.reranker_config_version,
                    manifest=config.manifest(),
                )
                .on_conflict_do_nothing(index_elements=["id"])
            )
            # A re-enqueued build of a failed generation resumes in place: the
            # atomic swap only promotes rows in the building state.
            connection.execute(
                sa.update(index_generations)
                .where(
                    index_generations.c.id == identity.generation_id,
                    index_generations.c.status == "failed",
                )
                .values(status="building", error_code=None)
            )

    def swap_ready(self, generation_id: uuid.UUID, chunk_count: int) -> None:
        """Atomically make this generation ready and supersede the prior one."""
        with self._engine.begin() as connection:
            generation = connection.execute(
                sa.select(index_generations).where(
                    index_generations.c.id == generation_id
                )
            ).mappings().first()
            if generation is None:
                raise LookupError(f"unknown index generation: {generation_id}")
            connection.execute(
                sa.update(index_generations)
                .where(
                    index_generations.c.source_version_id == generation["source_version_id"],
                    index_generations.c.status == "ready",
                    index_generations.c.id != generation_id,
                )
                .values(status="superseded")
            )
            connection.execute(
                sa.update(index_generations)
                .where(
                    index_generations.c.id == generation_id,
                    index_generations.c.status == "building",
                )
                .values(
                    status="ready",
                    chunk_count=chunk_count,
                    completed_at=sa.func.now(),
                    error_code=None,
                )
            )

    def mark_failed(self, generation_id: uuid.UUID, error_code: str) -> None:
        """Record an explicit generation failure."""
        with self._engine.begin() as connection:
            connection.execute(
                sa.update(index_generations)
                .where(index_generations.c.id == generation_id)
                .values(status="failed", error_code=error_code, completed_at=sa.func.now())
            )

    def purge_source(self, source_id: uuid.UUID) -> int:
        """Purge: delete every generation (chunk rows cascade) of one source."""
        with self._engine.begin() as connection:
            result = connection.execute(
                sa.delete(index_generations).where(
                    index_generations.c.source_id == source_id
                )
            )
        return result.rowcount
