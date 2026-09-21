"""
Retrieval use case (IDX-01, ch08): authorized hybrid search over index generations.

The port executes the constrained retrieval SQL (notebook + active/pinned
source versions + authorized source IDs) with the post-hydration policy
re-check and HNSW under-return over-fetch/retry. This use case fuses the
per-retriever rank lists with reciprocal-rank fusion - normalization within a
retriever only; raw lexical and vector scores are never compared with each
other.
"""

from __future__ import annotations

import itertools
import uuid
from dataclasses import dataclass, field
from typing import Protocol

from milpbooklm_domain.indexing import (
    FUSION_CONFIG_VERSION,
    RETRIEVER_LEXICAL,
    RETRIEVER_VECTOR,
    NodeSpan,
    RankedHit,
    reciprocal_rank_fusion,
)

from milpbooklm_application.indexing import IndexingEmbeddingClient, vector_to_text

VALID_MODES: frozenset[str] = frozenset({RETRIEVER_LEXICAL, RETRIEVER_VECTOR, "fused"})
MAX_TOP_K = 50


class RetrievalUnavailableError(RuntimeError):
    """The requested retrieval mode cannot run (e.g. no embedding client)."""


@dataclass(frozen=True, slots=True)
class RetrievalCommand:
    """One retrieval request (actor + notebook + query + mode + scope)."""

    actor_user_id: uuid.UUID
    notebook_id: uuid.UUID
    query: str
    language: str | None
    mode: str
    top_k: int
    source_ids: frozenset[uuid.UUID] | None = None


@dataclass(frozen=True, slots=True)
class RetrievedRow:
    """One hydrated, policy-rechecked row from a single retriever."""

    chunk_id: uuid.UUID
    notebook_id: uuid.UUID
    source_id: uuid.UUID
    source_version_id: uuid.UUID
    source_title: str
    canonical_node_id: uuid.UUID
    char_start: int
    char_end: int
    text: str
    token_count: int
    language: str
    section_ancestry: tuple[uuid.UUID, ...]
    node_spans: tuple[NodeSpan, ...]
    raw_score: float
    retriever_rank: int


class RetrievalPort(Protocol):
    """The constrained retrieval SQL (authz in query + post-hydration re-check)."""

    def search(
        self,
        command: RetrievalCommand,
        *,
        retriever: str,
        query_embedding_text: str | None,
    ) -> tuple[RetrievedRow, ...]:
        """Return ranked, hydrated rows (already policy-rechecked) for one retriever."""
        ...


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    """One final retrieval result (lexical/vector mode: the raw row; fused: RRF)."""

    row: RetrievedRow
    score: float
    rank: int
    retriever_scores: dict[str, float] = field(default_factory=dict)
    retriever_ranks: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RetrievalOutcome:
    """The retrieval result for one command."""

    mode: str
    fusion_config_version: str
    results: tuple[RetrievedChunk, ...]


class RetrieveChunks:
    """Run one retrieval: single retriever, or RRF fusion of lexical + vector."""

    def __init__(
        self,
        *,
        retrieval: RetrievalPort,
        embeddings: IndexingEmbeddingClient | None,
        expected_dimension: int | None,
    ) -> None:
        """Wire the retrieval port and the (optional) query-embedding client."""
        self._retrieval = retrieval
        self._embeddings = embeddings
        self._expected_dimension = expected_dimension

    def __call__(self, command: RetrievalCommand) -> RetrievalOutcome:
        """Execute the command and return the ranked outcome."""
        if command.mode not in VALID_MODES:
            raise ValueError(f"unsupported retrieval mode: {command.mode}")
        if command.top_k < 1 or command.top_k > MAX_TOP_K:
            raise ValueError("top_k must be within 1..50")
        if command.mode == RETRIEVER_LEXICAL:
            rows = self._retrieval.search(command, retriever=RETRIEVER_LEXICAL,
                                          query_embedding_text=None)
            return RetrievalOutcome(
                mode=command.mode,
                fusion_config_version=FUSION_CONFIG_VERSION,
                results=self._single_retriever(rows, RETRIEVER_LEXICAL),
            )
        if command.mode == RETRIEVER_VECTOR:
            rows = self._retrieval.search(
                command,
                retriever=RETRIEVER_VECTOR,
                query_embedding_text=self._query_embedding_text(command.query),
            )
            return RetrievalOutcome(
                mode=command.mode,
                fusion_config_version=FUSION_CONFIG_VERSION,
                results=self._single_retriever(rows, RETRIEVER_VECTOR),
            )
        return self._fused(command)

    def _fused(self, command: RetrievalCommand) -> RetrievalOutcome:
        lexical = self._retrieval.search(command, retriever=RETRIEVER_LEXICAL,
                                         query_embedding_text=None)
        vector = self._retrieval.search(
            command,
            retriever=RETRIEVER_VECTOR,
            query_embedding_text=self._query_embedding_text(command.query),
        )
        hits: list[RankedHit] = []
        rows_by_id: dict[uuid.UUID, RetrievedRow] = {}
        for row, retriever in itertools.chain(
            ((row, RETRIEVER_LEXICAL) for row in lexical),
            ((row, RETRIEVER_VECTOR) for row in vector),
        ):
            rows_by_id[row.chunk_id] = row
            hits.append(
                RankedHit(
                    chunk_id=row.chunk_id,
                    score=row.raw_score,
                    rank=row.retriever_rank,
                    retriever_id=retriever,
                )
            )
        fused = reciprocal_rank_fusion(tuple(hits))
        results: list[RetrievedChunk] = []
        for position, entry in enumerate(fused[: command.top_k], start=1):
            row = rows_by_id[entry.chunk_id]
            results.append(
                RetrievedChunk(
                    row=row,
                    score=entry.fused_score,
                    rank=position,
                    retriever_scores={hit.retriever_id: hit.score for hit in entry.hits},
                    retriever_ranks={hit.retriever_id: hit.rank for hit in entry.hits},
                )
            )
        return RetrievalOutcome(
            mode="fused",
            fusion_config_version=FUSION_CONFIG_VERSION,
            results=tuple(results),
        )

    @staticmethod
    def _single_retriever(
        rows: tuple[RetrievedRow, ...], retriever: str
    ) -> tuple[RetrievedChunk, ...]:
        return tuple(
            RetrievedChunk(
                row=row,
                score=row.raw_score,
                rank=row.retriever_rank,
                retriever_scores={retriever: row.raw_score},
                retriever_ranks={retriever: row.retriever_rank},
            )
            for row in rows
        )

    def _query_embedding_text(self, query: str) -> str:
        if self._embeddings is None or self._expected_dimension is None:
            raise RetrievalUnavailableError("vector retrieval requires an embedding client")
        (vector,) = self._embeddings.embed((query,), self._expected_dimension)
        return vector_to_text(vector)
