"""Deterministic and local OpenAI-compatible completion providers for RAG-01a."""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

import httpx
from milpbooklm_application.grounding import AnswerDraft, AnswerSpan, Evidence
from pydantic import BaseModel, ConfigDict

from milpbooklm_adapters.models.openai_schema import ChatChunkPayload

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
    """Scriptable completion seam that never resolves labels, URLs, or locators."""

    def __init__(self, scenario: FakeCompletionScenario = FakeCompletionScenario.VALID) -> None:
        """Choose the deterministic answer contract outcome."""
        self._scenario = scenario

    def complete(self, question: str, evidence: tuple[Evidence, ...]) -> AnswerDraft:
        """Return the selected deterministic response for the supplied evidence IDs."""
        match self._scenario:
            case FakeCompletionScenario.VALID:
                if not evidence:
                    return AnswerDraft((), insufficient_evidence=True)
                if question.startswith("Suggest three grounded starting questions"):
                    evidence_id = evidence[0].id
                    label = evidence[0].label
                    return AnswerDraft(
                        (
                            AnswerSpan(f"What is the main argument in {label}?", (evidence_id,)),
                            AnswerSpan(
                                f"Which evidence in {label} is most important?", (evidence_id,)
                            ),
                            AnswerSpan(
                                f"What should I investigate next in {label}?", (evidence_id,)
                            ),
                        )
                    )
                return AnswerDraft((AnswerSpan(evidence[0].text, (evidence[0].id,)),))
            case FakeCompletionScenario.INVENTED_EVIDENCE:
                return AnswerDraft((AnswerSpan("unsupported claim", ("invented-evidence-id",)),))
            case FakeCompletionScenario.INSUFFICIENT:
                return AnswerDraft((), insufficient_evidence=True)

    def stream(
        self, question: str, evidence: tuple[Evidence, ...]
    ) -> Generator[str, None, AnswerDraft]:
        """Yield deterministic answer text as best-effort word chunks."""
        draft = self.complete(question, evidence)
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

    def complete(self, question: str, evidence: tuple[Evidence, ...]) -> AnswerDraft:
        """Request structured spans whose citations can only be opaque evidence IDs."""
        with httpx.Client(base_url=self.base_url, timeout=120.0) as client:
            response = client.post("/chat/completions", json=self._payload(question, evidence))
            response.raise_for_status()
        envelope = _CompletionResponsePayload.model_validate_json(response.text)
        if not envelope.choices:
            raise GroundingCompletionError("completion response contains no choices")
        try:
            parsed = _AnswerPayload.model_validate_json(envelope.choices[0].message.content)
        except ValueError as error:
            raise GroundingCompletionError(
                "completion response is not an answer contract"
            ) from error
        return AnswerDraft(
            spans=tuple(AnswerSpan(span.text, span.evidence_ids) for span in parsed.spans),
            insufficient_evidence=parsed.insufficient_evidence,
        )

    def stream(
        self, question: str, evidence: tuple[Evidence, ...]
    ) -> Generator[str, None, AnswerDraft]:
        """Stream local provider deltas and return their completed structured draft."""
        payload = self._payload(question, evidence)
        payload["stream"] = True
        fragments: list[str] = []
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
                        yield choice.delta.content
        try:
            parsed = _AnswerPayload.model_validate_json("".join(fragments))
        except ValueError as error:
            raise GroundingCompletionError(
                "streamed completion is not an answer contract"
            ) from error
        return AnswerDraft(
            spans=tuple(AnswerSpan(span.text, span.evidence_ids) for span in parsed.spans),
            insufficient_evidence=parsed.insufficient_evidence,
        )

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

    def _payload(self, question: str, evidence: tuple[Evidence, ...]) -> dict[str, object]:
        return {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Answer only from evidence. Return JSON with spans [{text, evidence_ids}] "
                        "and insufficient_evidence. Cite only supplied IDs. "
                        "If insufficient, return "
                        '{"spans":[],"insufficient_evidence":true}.'
                    ),
                },
                {
                    "role": "user",
                    "content": "Question: "
                    + question
                    + "\nEvidence: "
                    + "\n".join(f"[{item.id}] {item.text}" for item in evidence),
                },
            ],
        }
