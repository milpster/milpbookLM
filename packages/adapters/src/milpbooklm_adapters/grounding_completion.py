"""Deterministic and local OpenAI-compatible completion providers for RAG-01a."""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, assert_never

import httpx
from milpbooklm_application.grounding import AnswerDraft, AnswerSpan, Evidence, NoteContext
from pydantic import BaseModel, ConfigDict

from milpbooklm_adapters.models.openai_schema import ChatChunkPayload
from milpbooklm_adapters.provider_health import ProviderHealth

LLAMA_CPP_COMPLETIONS_URL: Final = "http://127.0.0.1:8009/v1"
LLAMA_CPP_MODEL: Final = "/home/srcds/ai/ai/Swift-Qwen3.8-27B-Q6_K.gguf"


class GroundingCompletionError(RuntimeError):
    """The completion server returned a response outside the answer contract."""


class FakeCompletionScenario(StrEnum):
    """Stable fake outcomes for manual grounding QA."""

    VALID = "valid"
    INVENTED_EVIDENCE = "invented_evidence"
    INSUFFICIENT = "insufficient"


class FakeGroundingCompletionProvider:
    """Scriptable completion seam that uses only supplied server-owned context IDs."""

    def __init__(self, scenario: FakeCompletionScenario = FakeCompletionScenario.VALID) -> None:
        """Choose the deterministic answer contract outcome."""
        self._scenario = scenario

    def complete(
        self,
        question: str,
        evidence: tuple[Evidence, ...],
        note_contexts: tuple[NoteContext, ...] = (),
    ) -> AnswerDraft:
        """Return the selected deterministic response for supplied context IDs."""
        match self._scenario:
            case FakeCompletionScenario.VALID:
                if not evidence and not note_contexts:
                    return AnswerDraft((), insufficient_evidence=True)
                if evidence:
                    context_id = evidence[0].id
                    context_label = evidence[0].label
                    context_text = evidence[0].text
                else:
                    context_id = note_contexts[0].id
                    context_label = note_contexts[0].title
                    context_text = note_contexts[0].text
                if question.startswith("Suggest three grounded starting questions"):
                    return AnswerDraft(
                        (
                            AnswerSpan(
                                f"What is the main argument in {context_label}?",
                                (context_id,),
                            ),
                            AnswerSpan(
                                f"Which evidence in {context_label} is most important?",
                                (context_id,),
                            ),
                            AnswerSpan(
                                f"What should I investigate next in {context_label}?",
                                (context_id,),
                            ),
                        )
                    )
                return AnswerDraft((AnswerSpan(context_text, (context_id,)),))
            case FakeCompletionScenario.INVENTED_EVIDENCE:
                return AnswerDraft((AnswerSpan("unsupported claim", ("invented-evidence-id",)),))
            case FakeCompletionScenario.INSUFFICIENT:
                return AnswerDraft((), insufficient_evidence=True)
            case unreachable:
                assert_never(unreachable)

    def stream(
        self,
        question: str,
        evidence: tuple[Evidence, ...],
        note_contexts: tuple[NoteContext, ...] = (),
    ) -> Generator[str, None, AnswerDraft]:
        """Yield deterministic answer text as best-effort word chunks."""
        draft = self.complete(question, evidence, note_contexts)
        for span in draft.spans:
            for token in span.text.split(" "):
                yield f"{token} "
        return draft


class _SpanPayload(BaseModel):
    """Validated provider span with opaque server-issued evidence IDs only."""

    model_config = ConfigDict(frozen=True)

    text: str
    evidence_ids: tuple[str, ...]


class _AnswerPayload(BaseModel):
    """Validated JSON response from the completion model."""

    model_config = ConfigDict(frozen=True)

    spans: tuple[_SpanPayload, ...]
    insufficient_evidence: bool = False


class _ChoicePayload(BaseModel):
    """Minimal OpenAI-compatible non-streaming choice envelope."""

    model_config = ConfigDict(frozen=True)

    message: _MessagePayload


class _MessagePayload(BaseModel):
    """Minimal OpenAI-compatible message content envelope."""

    model_config = ConfigDict(frozen=True)

    content: str


class _CompletionResponsePayload(BaseModel):
    """Minimal OpenAI-compatible completion response envelope."""

    model_config = ConfigDict(frozen=True)

    choices: tuple[_ChoicePayload, ...]


@dataclass(frozen=True, slots=True)
class LlamaCppCompletionProvider:
    """Local OpenAI-compatible structured completion client for the GPU llama-server."""

    base_url: str = LLAMA_CPP_COMPLETIONS_URL
    model: str = LLAMA_CPP_MODEL
    health: ProviderHealth | None = None

    def complete(
        self,
        question: str,
        evidence: tuple[Evidence, ...],
        note_contexts: tuple[NoteContext, ...] = (),
    ) -> AnswerDraft:
        """Request structured spans citing only supplied opaque context IDs."""
        try:
            with httpx.Client(base_url=self.base_url, timeout=120.0) as client:
                response = client.post(
                    "/chat/completions", json=self._payload(question, evidence, note_contexts)
                )
                response.raise_for_status()
            envelope = _CompletionResponsePayload.model_validate_json(response.text)
            if not envelope.choices:
                raise GroundingCompletionError("completion response contains no choices")
            draft = _answer_draft(envelope.choices[0].message.content)
        except httpx.HTTPError:
            self._record_failure("transport")
            raise
        except (ValueError, GroundingCompletionError):
            self._record_failure("response")
            raise
        self._record_success()
        return draft

    def stream(
        self,
        question: str,
        evidence: tuple[Evidence, ...],
        note_contexts: tuple[NoteContext, ...] = (),
    ) -> Generator[str, None, AnswerDraft]:
        """Stream local provider deltas and return their completed structured draft."""
        payload = self._payload(question, evidence, note_contexts)
        payload["stream"] = True
        fragments: list[str] = []
        try:
            with (
                httpx.Client(base_url=self.base_url, timeout=120.0) as client,
                client.stream("POST", "/chat/completions", json=payload) as response,
            ):
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line.removeprefix("data: ")
                    if data == "[DONE]":
                        break
                    chunk = ChatChunkPayload.model_validate_json(data)
                    for choice in chunk.choices:
                        if choice.delta.content is not None:
                            fragments.append(choice.delta.content)
                            yield ""
            draft = _answer_draft("".join(fragments))
            for span in draft.spans:
                yield span.text
        except httpx.HTTPError:
            self._record_failure("transport")
            raise
        except (ValueError, GroundingCompletionError):
            self._record_failure("response")
            raise
        self._record_success()
        return draft

    def _record_success(self) -> None:
        if self.health is not None:
            self.health.record_success()

    def _record_failure(self, reason: str) -> None:
        if self.health is not None:
            self.health.record_failure(reason)

    def probe_models(self) -> tuple[str, ...]:
        """Confirm the local endpoint exposes a model before a grounded smoke run."""
        with httpx.Client(base_url=self.base_url, timeout=10.0) as client:
            response = client.get("/models")
            response.raise_for_status()
        payload = response.json()
        data = payload.get("data")
        if not isinstance(data, list):
            raise GroundingCompletionError("models response has no data list")
        return tuple(str(item["id"]) for item in data if isinstance(item, dict) and "id" in item)

    def _payload(
        self,
        question: str,
        evidence: tuple[Evidence, ...],
        note_contexts: tuple[NoteContext, ...],
    ) -> dict[str, object]:
        context_lines = [f"[{item.id}] {item.text}" for item in evidence]
        context_lines.extend(
            f"[{item.id}] Note '{item.title}': {item.text}" for item in note_contexts
        )
        return {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Answer only from supplied source evidence and explicitly selected note "
                        "contexts. Return JSON with spans [{text, evidence_ids}] and "
                        "insufficient_evidence. Cite only supplied IDs. If insufficient, return "
                        '{"spans":[],"insufficient_evidence":true}.'
                    ),
                },
                {
                    "role": "user",
                    "content": "Question: "
                    + question
                    + "\nContext: "
                    + "\n".join(context_lines),
                },
            ],
        }


def _answer_draft(content: str) -> AnswerDraft:
    """Parse the provider protocol once before any text crosses into chat presentation."""
    try:
        parsed = _AnswerPayload.model_validate_json(content)
    except ValueError as error:
        raise GroundingCompletionError("completion response is not an answer contract") from error
    return AnswerDraft(
        spans=tuple(AnswerSpan(span.text, span.evidence_ids) for span in parsed.spans),
        insufficient_evidence=parsed.insufficient_evidence,
    )
