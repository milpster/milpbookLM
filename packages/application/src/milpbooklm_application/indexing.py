"""
Index-generation build pipeline (IDX-01, ch08).

The pipeline is worker-driven and resumable: chunk (pure domain), persist
chunk rows under a pre-created generation ID (lexical), embed in deterministic
batches (model/dimension/normalization recorded in the generation manifest),
reject a provider dimension mismatch (a dimension change is a NEW parallel
generation - never an in-place reinterpretation), and swap the generation to
``ready`` atomically (the prior ready generation of the same source version
is superseded in the same transaction).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from milpbooklm_contracts.canonical_document import CanonicalDocument
from milpbooklm_domain.indexing import (
    FUSION_CONFIG_VERSION,
    Chunk,
    ChunkerProfile,
)

from milpbooklm_application.chunking import chunk_document

logger = logging.getLogger(__name__)

DEFAULT_EMBEDDING_BATCH_SIZE = 32
DEFAULT_EMBEDDING_NORMALIZATION = "l2"


class IndexGenerationError(RuntimeError):
    """An index generation cannot be built (explicit failure, never a silent partial)."""


class EmbeddingDimensionMismatchError(IndexGenerationError):
    """The provider returned vectors of a dimension the generation does not record."""


@dataclass(frozen=True, slots=True)
class EmbeddingSpec:
    """Recorded embedding space identity: model, ref, dimension, normalization."""

    model: str
    model_ref: str | None
    dimension: int
    normalization: str
    batch_size: int = DEFAULT_EMBEDDING_BATCH_SIZE


@dataclass(frozen=True, slots=True)
class IndexBuildConfig:
    """One index generation's full configuration (versioned, manifest-pinned)."""

    profile: ChunkerProfile
    embedding: EmbeddingSpec
    fusion_config_version: str = FUSION_CONFIG_VERSION
    reranker_config_version: str | None = None

    def manifest(self) -> dict[str, object]:
        """Return the immutable generation manifest (fusion/reranker version included)."""
        return {
            "schema": 1,
            "chunker": {
                "profile": self.profile.name,
                "revision": self.profile.revision,
                "max_tokens": self.profile.max_tokens,
                "token_estimator": self.profile.token_estimator,
            },
            "lexical": {
                "engine": "postgresql-fts",
                "ranker": "ts_rank",
                "note": "native PostgreSQL FTS ranking (intentionally not labeled BM25)",
            },
            "embedding": {
                "model": self.embedding.model,
                "model_ref": self.embedding.model_ref,
                "dimension": self.embedding.dimension,
                "normalization": self.embedding.normalization,
                "batch_size": self.embedding.batch_size,
            },
            "fusion": {
                "config_version": self.fusion_config_version,
                "method": "reciprocal-rank",
                "reranker": self.reranker_config_version,
            },
        }


def config_to_payload(config: IndexBuildConfig) -> dict[str, object]:
    """Serialize the build config into a durable job payload (content-free)."""
    return {
        "profile_name": config.profile.name,
        "profile_revision": config.profile.revision,
        "max_tokens": config.profile.max_tokens,
        "token_estimator": config.profile.token_estimator,
        "model": config.embedding.model,
        "model_ref": config.embedding.model_ref,
        "dimension": config.embedding.dimension,
        "normalization": config.embedding.normalization,
        "batch_size": config.embedding.batch_size,
        "fusion_config_version": config.fusion_config_version,
        "reranker_config_version": config.reranker_config_version,
    }


def _payload_int(payload: dict[str, object], key: str) -> int:
    value = payload[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"payload {key} must be an int")
    return value


def config_from_payload(payload: dict[str, object]) -> IndexBuildConfig:
    """Parse a build config from a job payload (typed boundary)."""
    profile = ChunkerProfile(
        name=str(payload["profile_name"]),
        revision=str(payload["profile_revision"]),
        max_tokens=_payload_int(payload, "max_tokens"),
        token_estimator=str(payload["token_estimator"]),
    )
    embedding = EmbeddingSpec(
        model=str(payload["model"]),
        model_ref=None if payload["model_ref"] is None else str(payload["model_ref"]),
        dimension=_payload_int(payload, "dimension"),
        normalization=str(payload["normalization"]),
        batch_size=_payload_int(payload, "batch_size"),
    )
    reranker = payload["reranker_config_version"]
    return IndexBuildConfig(
        profile=profile,
        embedding=embedding,
        fusion_config_version=str(payload["fusion_config_version"]),
        reranker_config_version=None if reranker is None else str(reranker),
    )


def vector_to_text(vector: tuple[float, ...]) -> str:
    """Render a vector as pgvector's text form (the raw-SQL binding boundary)."""
    return "[" + ",".join(repr(float(item)) for item in vector) + "]"


GENERATION_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "milpbooklm.local/index-generation")


def generation_id_for(
    source_version_id: uuid.UUID, model: str, dimension: int, profile_revision: str
) -> uuid.UUID:
    """
    Derive the deterministic generation ID for one (version, space, profile) tuple.

    Determinism makes re-enqueue resume the SAME generation (idempotent build),
    while a model/dimension/profile change derives a NEW generation (parallel,
    atomic swap - never an in-place reinterpretation).
    """
    return uuid.uuid5(
        GENERATION_NAMESPACE,
        f"index:{source_version_id}:{model}:{dimension}:{profile_revision}",
    )


def idempotency_key_for(
    source_version_id: uuid.UUID, model: str, dimension: int, profile_revision: str
) -> str:
    """Return the enqueue idempotency key for one (version, space, profile) tuple."""
    return f"index:{source_version_id}:{model}:{dimension}:{profile_revision}"


@dataclass(frozen=True, slots=True)
class GenerationIdentity:
    """The immutable identity of one index generation (pre-created at enqueue)."""

    generation_id: uuid.UUID
    notebook_id: uuid.UUID
    source_id: uuid.UUID
    source_version_id: uuid.UUID
    canonical_document_id: uuid.UUID


class GenerationStore(Protocol):
    """Generation lifecycle persistence (create, swap, fail, purge)."""

    def get_status(self, generation_id: uuid.UUID) -> str | None:
        """Return the generation status (None when absent)."""
        ...

    def create(self, identity: GenerationIdentity, config: IndexBuildConfig) -> None:
        """Create the generation row with its immutable manifest (idempotent)."""
        ...

    def swap_ready(self, generation_id: uuid.UUID, chunk_count: int) -> None:
        """Atomically make this generation ready and supersede the prior one."""
        ...

    def mark_failed(self, generation_id: uuid.UUID, error_code: str) -> None:
        """Record an explicit generation failure."""
        ...

    def purge_source(self, source_id: uuid.UUID) -> int:
        """Purge: delete every generation (and its rows) of one source (T24 seam)."""
        ...


class ChunkStore(Protocol):
    """Chunk-row persistence under a generation (resumable, idempotent)."""

    def existing_chunk_ids(self, generation_id: uuid.UUID) -> frozenset[uuid.UUID]:
        """Return the chunk IDs already persisted for the generation (resume check)."""
        ...

    def insert_chunks(
        self, generation_id: uuid.UUID, document: CanonicalDocument, chunks: tuple[Chunk, ...]
    ) -> int:
        """Persist chunk rows (lexical); skip IDs already present; return inserted count."""
        ...

    def set_embedding(
        self, generation_id: uuid.UUID, chunk_id: uuid.UUID, vector_text: str
    ) -> None:
        """Attach one vector (text form) to a chunk row of the generation."""
        ...


class CanonicalDocumentReader(Protocol):
    """Reads a persisted canonical document (the chunking input)."""

    def load(self, document_id: uuid.UUID) -> CanonicalDocument:
        """Load the document contract; raises when absent."""
        ...


class IndexingEmbeddingClient(Protocol):
    """
    Synchronous batch embedding client behind the indexing pipeline.

    Prototype deviation (recorded): a direct local llama.cpp call instead of the
    async streaming ``EmbeddingProvider`` port - the worker loop is synchronous
    and the orchestrator (T10) is design-only at this stage.
    """

    def embed(
        self, texts: tuple[str, ...], expected_dimension: int
    ) -> tuple[tuple[float, ...], ...]:
        """Embed one deterministic batch; raise EmbeddingDimensionMismatchError on drift."""
        ...


ProgressCallback = Callable[[str, int, int, str | None], None]


class BuildSourceIndex:
    """The resumable generation build: chunk, persist, embed, atomic swap."""

    def __init__(
        self,
        *,
        generations: GenerationStore,
        chunks: ChunkStore,
        documents: CanonicalDocumentReader,
        embeddings: IndexingEmbeddingClient,
    ) -> None:
        """Wire the generation store, chunk store, document reader, and client."""
        self._generations = generations
        self._chunks = chunks
        self._documents = documents
        self._embeddings = embeddings

    def run(
        self,
        identity: GenerationIdentity,
        config: IndexBuildConfig,
        progress: ProgressCallback | None = None,
    ) -> int:
        """Build (or resume) the generation; return its chunk count."""
        status = self._generations.get_status(identity.generation_id)
        if status == "ready":
            return self._chunk_count(identity.generation_id)
        if status is None or status == "failed":
            self._generations.create(identity, config)
        document = self._documents.load(identity.canonical_document_id)
        if document.source_version_id != identity.source_version_id:
            raise IndexGenerationError(
                "canonical document belongs to a different source version"
            )
        report = progress
        if report is not None:
            report("chunking", 0, 1, "structural chunking")
        chunks = chunk_document(document, config.profile)
        existing = self._chunks.existing_chunk_ids(identity.generation_id)
        pending = tuple(chunk for chunk in chunks if chunk.chunk_id not in existing)
        if pending:
            inserted = self._chunks.insert_chunks(identity.generation_id, document, pending)
            if report is not None:
                report("lexical", inserted, len(pending), "chunk rows persisted")
        done = 0
        for start in range(0, len(pending), config.embedding.batch_size):
            batch = pending[start : start + config.embedding.batch_size]
            vectors = self._embeddings.embed(
                tuple(chunk.text for chunk in batch), config.embedding.dimension
            )
            for chunk, vector in zip(batch, vectors, strict=True):
                self._chunks.set_embedding(
                    identity.generation_id, chunk.chunk_id, vector_to_text(vector)
                )
            done += len(batch)
            if report is not None:
                report("embedding", done, len(pending), "bge-m3 batch embedded")
        self._generations.swap_ready(identity.generation_id, len(chunks))
        logger.info(
            "index generation %s ready (%d chunks, model=%s dim=%d)",
            identity.generation_id,
            len(chunks),
            config.embedding.model,
            config.embedding.dimension,
        )
        return len(chunks)

    def mark_generation_failed(self, generation_id: uuid.UUID, error_code: str) -> None:
        """Record an explicit generation failure (handler seam)."""
        self._generations.mark_failed(generation_id, error_code)

    def _chunk_count(self, generation_id: uuid.UUID) -> int:
        return len(self._chunks.existing_chunk_ids(generation_id))
