"""
Chunking configuration and retrieval fusion primitives (IDX-01, ch08).

Pure domain logic (stdlib only): the versioned chunker profile, the model-
independent token estimator, the FTS language mapping, the chunk/span value
objects, and reciprocal-rank fusion over per-retriever rank lists (normalization
happens within a retriever only - raw lexical and vector scores are never
compared). The canonical-tree chunking mechanics themselves live in the
application layer (chunking.py), where the canonical-document contract types
are allowed.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from typing import Final

_WORD_TOKEN: Final = re.compile(r"\S+")
FTS_FALLBACK_CONFIG: Final = "simple"
_FTS_CONFIGS: Final[dict[str, str]] = {"en": "english", "de": "german"}
_RRF_K_DEFAULT: Final = 60
FUSION_CONFIG_VERSION: Final = "rrf-v1"
RETRIEVER_LEXICAL: Final = "lexical"
RETRIEVER_VECTOR: Final = "vector"
_TOKEN_ESTIMATOR_V1: Final = "whitespace-word-v1"  # noqa: S105


def estimate_tokens(text: str) -> int:
    """Model-independent token estimate (whitespace-delimited words, estimator v1)."""
    return len(_WORD_TOKEN.findall(text))


@dataclass(frozen=True, slots=True)
class ChunkerProfile:
    """Versioned, model-independent chunking configuration."""

    name: str
    revision: str
    max_tokens: int
    token_estimator: str = _TOKEN_ESTIMATOR_V1


STRUCTURAL_CHUNKER_V1: Final = ChunkerProfile(name="structural", revision="1", max_tokens=400)


def fts_config_for_language(language: str | None) -> str:
    """Map a chunk language to its PG text-search config (explicit fallback)."""
    if language is None:
        return FTS_FALLBACK_CONFIG
    base = language.lower().split("-")[0]
    return _FTS_CONFIGS.get(base, FTS_FALLBACK_CONFIG)


@dataclass(frozen=True, slots=True)
class NodeSpan:
    """A character span within one canonical node's text (citation-jump target)."""

    node_id: uuid.UUID
    char_start: int
    char_end: int


@dataclass(frozen=True, slots=True)
class Chunk:
    """One structural chunk: stable ID, primary node/span, full node map, context."""

    chunk_id: uuid.UUID
    node_id: uuid.UUID
    char_start: int
    char_end: int
    text: str
    token_count: int
    language: str
    section_ancestry: tuple[uuid.UUID, ...]
    node_spans: tuple[NodeSpan, ...]
    order: int
    prev_chunk_id: uuid.UUID | None = None
    next_chunk_id: uuid.UUID | None = None
    text_checksum: str = field(default="")

    def __post_init__(self) -> None:
        """Derive the text checksum once (frozen slots)."""
        if not self.text_checksum:
            object.__setattr__(
                self, "text_checksum", hashlib.sha256(self.text.encode("utf-8")).hexdigest()
            )


@dataclass(frozen=True, slots=True)
class RankedHit:
    """One retriever's ranked output entry (rank is the within-retriever position)."""

    chunk_id: uuid.UUID
    score: float
    rank: int
    retriever_id: str


@dataclass(frozen=True, slots=True)
class FusedChunk:
    """One fused result: reciprocal-rank sum over the contributing retrievers."""

    chunk_id: uuid.UUID
    fused_score: float
    hits: tuple[RankedHit, ...]


def reciprocal_rank_fusion(
    hits: tuple[RankedHit, ...], k: int = _RRF_K_DEFAULT
) -> tuple[FusedChunk, ...]:
    """Fuse per-retriever rank lists (RRF, k configurable; within-retriever only)."""
    if k < 1:
        raise ValueError("RRF k must be >= 1")
    grouped: dict[uuid.UUID, list[RankedHit]] = {}
    for hit in hits:
        grouped.setdefault(hit.chunk_id, []).append(hit)
    fused: list[FusedChunk] = []
    for chunk_id, group in grouped.items():
        score = sum(1.0 / (k + hit.rank) for hit in group)
        fused.append(FusedChunk(chunk_id=chunk_id, fused_score=score, hits=tuple(group)))
    fused.sort(key=lambda item: (-item.fused_score, item.chunk_id))
    return tuple(fused)
