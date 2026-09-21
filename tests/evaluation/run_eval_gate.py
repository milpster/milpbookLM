"""Run EVAL-GATE-001 v1 over locked corpora and live bge-m3 embeddings."""

from __future__ import annotations

import argparse
import hashlib
import math
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict

ROOT = Path(__file__).parent
CORPUS_ROOT = ROOT / "corpora" / "v1"


class LockedModel(BaseModel):
    """Reject schema drift in versioned evaluation inputs."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class EmbeddingChunk(LockedModel):
    id: str
    language: Literal["de", "en"]
    text: str


class EmbeddingJudgment(LockedModel):
    id: str
    language: Literal["de", "en"]
    query: str
    expected_chunk_id: str


class EmbeddingCorpus(LockedModel):
    version: Literal["v1"]
    chunks: tuple[EmbeddingChunk, ...]
    judgments: tuple[EmbeddingJudgment, ...]


class LabeledItem(LockedModel):
    id: str
    language: Literal["de", "en"]
    evidence: str | None = None
    question: str | None = None
    answerable: bool | None = None
    left: str | None = None
    right: str | None = None
    contradiction: bool | None = None
    claim: str | None = None
    entailed: bool | None = None
    case: str | None = None
    scores: tuple[int, int, int] | None = None


class LabeledCorpus(LockedModel):
    version: Literal["v1"]
    kind: str
    rubric: tuple[str, ...] | None = None
    items: tuple[LabeledItem, ...]


class EmbeddingThresholds(LockedModel):
    model: str
    dimension: int
    recall_k: int
    minimum_recall: float
    minimum_recall_de: float
    minimum_recall_en: float


class ChatThresholds(LockedModel):
    dimensions: tuple[str, str, str]
    minimum_locked_judgment_score: float
    minimum_live_factuality_with_citation: float
    minimum_live_language_quality: float
    minimum_live_refusal: float


class Conformance(LockedModel):
    profile: Literal["EVAL-GATE-001-v1"]
    corpus_version: Literal["v1"]
    minimum_items_per_language_per_kind: int
    embedding: EmbeddingThresholds
    chat_quality_rubric: ChatThresholds


class EmbeddingDatum(LockedModel):
    index: int
    object: Literal["embedding"]
    embedding: tuple[float, ...]


class EmbeddingResponse(LockedModel):
    model: str
    object: str
    data: tuple[EmbeddingDatum, ...]
    usage: dict[str, int]


class GateReport(LockedModel):
    gate: str
    status: Literal["pass", "fail"]
    corpus_version: str
    corpus_sha256: dict[str, str]
    counts: dict[str, dict[str, int]]
    embedding_dimension: int
    recall_at_k: dict[str, float]
    locked_judgment_score: float


def _load_model[T: BaseModel](path: Path, model: type[T]) -> T:
    return model.model_validate_json(path.read_text(encoding="utf-8"))


def _counts(items: tuple[LabeledItem, ...] | tuple[EmbeddingJudgment, ...]) -> dict[str, int]:
    return {
        language: sum(item.language == language for item in items)
        for language in ("de", "en")
    }


def _embed(base_url: str, texts: list[str]) -> tuple[tuple[float, ...], ...]:
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=60.0) as client:
        response = client.post("/embeddings", json={"model": "bge-m3", "input": texts})
        response.raise_for_status()
    payload = EmbeddingResponse.model_validate_json(response.text)
    return tuple(item.embedding for item in sorted(payload.data, key=lambda item: item.index))


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return numerator / (left_norm * right_norm)


def _recall(
    corpus: EmbeddingCorpus,
    vectors: tuple[tuple[float, ...], ...],
    *,
    k: int,
) -> dict[str, float]:
    chunk_vectors = vectors[: len(corpus.chunks)]
    query_vectors = vectors[len(corpus.chunks) :]
    hits: dict[str, list[bool]] = {"de": [], "en": []}
    for judgment, query_vector in zip(corpus.judgments, query_vectors, strict=True):
        ranked = sorted(
            zip(corpus.chunks, chunk_vectors, strict=True),
            key=lambda pair: _cosine(query_vector, pair[1]),
            reverse=True,
        )
        hits[judgment.language].append(
            judgment.expected_chunk_id in {chunk.id for chunk, _ in ranked[:k]}
        )
    all_hits = hits["de"] + hits["en"]
    return {
        "overall": sum(all_hits) / len(all_hits),
        "de": sum(hits["de"]) / len(hits["de"]),
        "en": sum(hits["en"]) / len(hits["en"]),
    }


def run(base_url: str) -> GateReport:
    conformance = _load_model(ROOT / "conformance-v1.json", Conformance)
    embedding = _load_model(CORPUS_ROOT / "embedding-recall.json", EmbeddingCorpus)
    corpus_paths = tuple(sorted(CORPUS_ROOT.glob("*.json")))
    labeled = {
        path.stem: _load_model(path, LabeledCorpus)
        for path in corpus_paths
        if path.name != "embedding-recall.json"
    }
    counts = {name: _counts(corpus.items) for name, corpus in labeled.items()}
    counts["embedding-recall"] = _counts(embedding.judgments)
    count_ok = all(
        count >= conformance.minimum_items_per_language_per_kind
        for language_counts in counts.values()
        for count in language_counts.values()
    )
    texts = [chunk.text for chunk in embedding.chunks]
    texts.extend(judgment.query for judgment in embedding.judgments)
    vectors = _embed(base_url, texts)
    dimension = len(vectors[0])
    recall = _recall(embedding, vectors, k=conformance.embedding.recall_k)
    judgments = labeled["judgments"].items
    scores = [score for item in judgments for score in (item.scores or ())]
    locked_score = sum(scores) / len(scores)
    threshold_ok = (
        dimension == conformance.embedding.dimension
        and recall["overall"] >= conformance.embedding.minimum_recall
        and recall["de"] >= conformance.embedding.minimum_recall_de
        and recall["en"] >= conformance.embedding.minimum_recall_en
        and locked_score >= conformance.chat_quality_rubric.minimum_locked_judgment_score
    )
    hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in corpus_paths
    }
    return GateReport(
        gate=conformance.profile,
        status="pass" if count_ok and threshold_ok else "fail",
        corpus_version=conformance.corpus_version,
        corpus_sha256=hashes,
        counts=counts,
        embedding_dimension=dimension,
        recall_at_k=recall,
        locked_judgment_score=locked_score,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embedding-url", default="http://127.0.0.1:8010/v1")
    parser.add_argument("--report", type=Path, default=ROOT / "report-v1.json")
    arguments = parser.parse_args()
    report = run(arguments.embedding_url)
    arguments.report.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(report.model_dump_json(indent=2))
    return 0 if report.status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
