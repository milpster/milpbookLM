"""Grounded-answer orchestration: retrieve, assemble, validate, then publish."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Generator
from dataclasses import dataclass
from typing import Final, Protocol

from milpbooklm_application.retrieval import RetrievalCommand, RetrieveChunks, RetrievedChunk

DEFAULT_CANDIDATE_COUNT = 30
DEFAULT_CONTEXT_TOKEN_BUDGET = 2_000
DEFAULT_PER_SOURCE_QUOTA = 2
LLAMA_CPP_MODEL: Final = "/home/srcds/ai/ai/Swift-Qwen3.8-27B-Q6_K.gguf"


class GroundingError(RuntimeError):
    """A grounded draft cannot be published."""


@dataclass(frozen=True, slots=True)
class NoteContext:
    """One explicitly selected immutable note revision exposed to completion."""

    id: str
    note_id: uuid.UUID
    revision_id: uuid.UUID
    title: str
    text: str


@dataclass(frozen=True, slots=True)
class FrozenManifest:
    """The immutable source and explicit-note scope captured before generation."""

    id: uuid.UUID
    source_version_ids: frozenset[uuid.UUID]
    note_contexts: tuple[NoteContext, ...] = ()


@dataclass(frozen=True, slots=True)
class Evidence:
    """Server-owned evidence identity exposed to a completion provider."""

    id: str
    chunk_id: uuid.UUID
    source_id: uuid.UUID
    source_version_id: uuid.UUID
    canonical_node_id: uuid.UUID
    char_start: int
    char_end: int
    label: str
    text: str
    token_count: int


@dataclass(frozen=True, slots=True)
class AnswerSpan:
    """One claim-sized answer span and the evidence IDs that support it."""

    text: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AnswerDraft:
    """Provider output contract. Labels, URLs and locators are intentionally absent."""

    spans: tuple[AnswerSpan, ...]
    insufficient_evidence: bool = False


@dataclass(frozen=True, slots=True)
class GroundingRequest:
    """One grounded answer request with sources and optional explicit note revisions."""

    actor_user_id: uuid.UUID
    notebook_id: uuid.UUID
    conversation_id: uuid.UUID
    question: str
    context_message_ids: tuple[uuid.UUID, ...] = ()
    selected_source_ids: frozenset[uuid.UUID] | None = None
    selected_note_revision_ids: tuple[uuid.UUID, ...] = ()
    chat_config_snapshot: dict[str, str] | None = None
    instructions_snapshot: str = ""
    token_budget: int = DEFAULT_CONTEXT_TOKEN_BUDGET


@dataclass(frozen=True, slots=True)
class GroundedAnswer:
    """Published answer metadata suitable for the future chat surface."""

    message_id: uuid.UUID | None
    manifest_id: uuid.UUID
    spans: tuple[AnswerSpan, ...]
    citations: tuple[Evidence, ...]
    insufficient_evidence: bool


@dataclass(frozen=True, slots=True)
class PreparedGroundedAnswer:
    """Retrieved evidence held transiently until validated publication."""

    request: GroundingRequest
    manifest: FrozenManifest
    evidence: tuple[Evidence, ...]
    retrieval_trace: str


class CompletionProvider(Protocol):
    """A completion boundary that receives only server-issued context identities."""

    def complete(
        self,
        question: str,
        evidence: tuple[Evidence, ...],
        note_contexts: tuple[NoteContext, ...] = (),
    ) -> AnswerDraft:
        """Return structured spans citing supplied source or note context IDs only."""
        ...

    def stream(
        self,
        question: str,
        evidence: tuple[Evidence, ...],
        note_contexts: tuple[NoteContext, ...] = (),
    ) -> Generator[str, None, AnswerDraft]:
        """Yield best-effort tokens and return the completed structured answer."""
        ...


class GroundingStore(Protocol):
    """Persistence and deterministic citation validation boundary."""

    def freeze(self, *, request: GroundingRequest, normalized_question: str) -> FrozenManifest:
        """Persist the immutable actor, context, and source-version selection."""
        ...

    def publish(
        self,
        *,
        request: GroundingRequest,
        manifest: FrozenManifest,
        evidence: tuple[Evidence, ...],
        draft: AnswerDraft,
        retrieval_trace: str,
    ) -> GroundedAnswer:
        """Freeze manifest, validate citations, and atomically publish the answer."""
        ...

    def abstain(
        self,
        *,
        request: GroundingRequest,
        manifest: FrozenManifest,
        retrieval_trace: str,
        content: str,
    ) -> GroundedAnswer:
        """Publish a transparent limitation without unsupported claims or citations."""
        ...

    def jump(
        self,
        *,
        actor_user_id: uuid.UUID,
        source_version_id: uuid.UUID,
        canonical_node_id: uuid.UUID,
    ) -> dict[str, str | int | tuple[float, ...]]:
        """Resolve a pinned evidence locator under current authorization."""
        ...


class GenerateGroundedAnswer:
    """The six-step source retrieval plus explicit pinned-note pipeline."""

    def __init__(
        self,
        *,
        retrieval: RetrieveChunks,
        completion: CompletionProvider,
        store: GroundingStore,
    ) -> None:
        """Wire reusable retrieval, a provider seam, and atomic publication."""
        self._retrieval = retrieval
        self._completion = completion
        self._store = store

    def __call__(self, request: GroundingRequest) -> GroundedAnswer:
        """Freeze intent, retrieve/fuse, assemble, generate, validate, and publish."""
        normalized_question = self._normalize(request.question)
        manifest = self._store.freeze(request=request, normalized_question=normalized_question)
        return self.generate(request, manifest)

    def generate(self, request: GroundingRequest, manifest: FrozenManifest) -> GroundedAnswer:
        """Generate against an already-frozen manifest without creating a second snapshot."""
        prepared = self.prepare(request, manifest)
        if not prepared.evidence and not manifest.note_contexts:
            return self._abstain(prepared)
        return self._publish(prepared)

    def stream_generate(
        self,
        request: GroundingRequest,
        manifest: FrozenManifest,
        cancelled: Callable[[], bool],
    ) -> Generator[str, None, GroundedAnswer | None]:
        """Present provider tokens, then publish only the completed validated draft."""
        prepared = self.prepare(request, manifest)
        if not prepared.evidence and not manifest.note_contexts:
            return self._abstain(prepared)
        generation = self._completion.stream(
            request.question, prepared.evidence, manifest.note_contexts
        )
        while True:
            try:
                token = next(generation)
            except StopIteration as completed:
                draft = completed.value
                break
            if cancelled():
                return None
            yield token
        if cancelled():
            return None
        return self._publish(prepared, draft)

    def prepare(
        self, request: GroundingRequest, manifest: FrozenManifest
    ) -> PreparedGroundedAnswer:
        """Perform the grounded retrieval phase before token presentation begins."""
        normalized_question = self._normalize(request.question)
        if not manifest.source_version_ids:
            trace = "note-context-only" if manifest.note_contexts else "no-selected-sources"
            return PreparedGroundedAnswer(request, manifest, (), trace)
        outcome = self._retrieval(
            RetrievalCommand(
                actor_user_id=request.actor_user_id,
                notebook_id=request.notebook_id,
                query=normalized_question,
                language=None,
                mode="fused",
                top_k=DEFAULT_CANDIDATE_COUNT,
                source_ids=request.selected_source_ids,
                source_version_ids=manifest.source_version_ids,
            )
        )
        evidence = self._assemble(outcome.results, request.token_budget)
        trace = f"{outcome.fusion_config_version}:reranker=absent"
        return PreparedGroundedAnswer(request, manifest, evidence, trace)

    def _publish(
        self, prepared: PreparedGroundedAnswer, draft: AnswerDraft | None = None
    ) -> GroundedAnswer:
        """Validate and atomically persist the completed structured answer."""
        completed_draft = (
            self._completion.complete(
                prepared.request.question,
                prepared.evidence,
                prepared.manifest.note_contexts,
            )
            if draft is None
            else draft
        )
        if completed_draft.insufficient_evidence:
            if completed_draft.spans:
                raise GroundingError("an insufficiency draft must not contain factual spans")
            return self._abstain(prepared)
        return self._store.publish(
            request=prepared.request,
            manifest=prepared.manifest,
            evidence=prepared.evidence,
            draft=completed_draft,
            retrieval_trace=prepared.retrieval_trace,
        )

    def _abstain(self, prepared: PreparedGroundedAnswer) -> GroundedAnswer:
        """Publish useful, non-factual guidance when the frozen context cannot support an answer."""
        language = (prepared.request.chat_config_snapshot or {}).get("output_language", "EN")
        content = (
            "Ich kann diese Frage mit den verfügbaren Belegen nicht beantworten. "
            + "Füge eine Quelle oder Notiz hinzu oder wähle eine aus, die die Frage direkt "
            + "behandelt, und versuche es erneut."
            if language == "DE"
            else "I can't answer this from the available evidence. Add or select a source or note "
            + "that directly addresses the question, then try again."
        )
        return self._store.abstain(
            request=prepared.request,
            manifest=prepared.manifest,
            retrieval_trace=prepared.retrieval_trace,
            content=content,
        )

    def freeze(self, request: GroundingRequest) -> FrozenManifest:
        """Expose the immutable pre-turn manifest needed by conversation history."""
        return self._store.freeze(
            request=request,
            normalized_question=self._normalize(request.question),
        )

    @staticmethod
    def _normalize(question: str) -> str:
        """Use deterministic whitespace normalization rather than an unrecorded sub-call."""
        normalized = " ".join(question.split())
        if not normalized:
            raise GroundingError("question must not be blank")
        return normalized

    @staticmethod
    def _assemble(results: tuple[RetrievedChunk, ...], token_budget: int) -> tuple[Evidence, ...]:
        """Apply stable rank ordering, per-source quota, diversity, and token budget."""
        if token_budget < 1:
            raise GroundingError("token budget must be positive")
        selected: list[Evidence] = []
        per_source: dict[uuid.UUID, int] = {}
        used_tokens = 0
        for entry in results:
            row = entry.row
            count = per_source.get(row.source_id, 0)
            if count >= DEFAULT_PER_SOURCE_QUOTA:
                continue
            if used_tokens + row.token_count > token_budget:
                continue
            evidence = Evidence(
                id=f"e{len(selected) + 1}",
                chunk_id=row.chunk_id,
                source_id=row.source_id,
                source_version_id=row.source_version_id,
                canonical_node_id=row.canonical_node_id,
                char_start=row.char_start,
                char_end=row.char_end,
                label=row.source_title,
                text=row.text,
                token_count=row.token_count,
            )
            selected.append(evidence)
            per_source[row.source_id] = count + 1
            used_tokens += row.token_count
        return tuple(selected)
