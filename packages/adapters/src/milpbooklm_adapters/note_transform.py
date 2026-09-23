"""Completion-backed transforms over immutable note revisions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import assert_never

import httpx
from milpbooklm_application.note_core import (
    NoteRevisionView,
    NoteTransformKind,
    note_content_text,
)
from pydantic import BaseModel, ConfigDict, Field

from milpbooklm_adapters.grounding_completion import (
    LLAMA_CPP_COMPLETIONS_URL,
    LLAMA_CPP_MODEL,
    GroundingCompletionError,
)


class _TransformPayload(BaseModel):
    """Validated structured note content returned by the completion model."""

    model_config = ConfigDict(frozen=True)

    content: dict[str, object] = Field(min_length=1)


class _MessagePayload(BaseModel):
    """Minimal OpenAI-compatible assistant message."""

    model_config = ConfigDict(frozen=True)

    content: str


class _ChoicePayload(BaseModel):
    """Minimal OpenAI-compatible completion choice."""

    model_config = ConfigDict(frozen=True)

    message: _MessagePayload


class _CompletionPayload(BaseModel):
    """Minimal OpenAI-compatible completion envelope."""

    model_config = ConfigDict(frozen=True)

    choices: tuple[_ChoicePayload, ...]


@dataclass(frozen=True, slots=True)
class FakeNoteTransformProvider:
    """Deterministic transform provider for explicit fake-provider installations."""

    def transform(
        self, kind: NoteTransformKind, revisions: tuple[NoteRevisionView, ...]
    ) -> dict[str, object]:
        """Return predictable rich-note content from the exact selected revisions."""
        selected = "\n".join(note_content_text(revision.content) for revision in revisions)
        return {
            "blocks": [
                {
                    "type": "paragraph",
                    "text": f"{kind.value}: {selected}",
                }
            ]
        }


@dataclass(frozen=True, slots=True)
class LlamaCppNoteTransformProvider:
    """Transform selected note revisions through the configured local completion endpoint."""

    base_url: str = LLAMA_CPP_COMPLETIONS_URL
    model: str = LLAMA_CPP_MODEL
    transport: httpx.BaseTransport | None = None

    def transform(
        self, kind: NoteTransformKind, revisions: tuple[NoteRevisionView, ...]
    ) -> dict[str, object]:
        """Return validated rich-note JSON for one supported transform kind."""
        match kind:
            case NoteTransformKind.COMBINE:
                instruction = (
                    "Combine the selected notes into one coherent note without repetition."
                )
            case NoteTransformKind.CRITIQUE:
                instruction = (
                    "Critique the selected notes, separating strengths, gaps, and next steps."
                )
            case NoteTransformKind.SUMMARIZE:
                instruction = "Summarize the selected notes while retaining their key claims."
            case NoteTransformKind.OUTLINE:
                instruction = "Turn the selected notes into a hierarchical outline."
            case NoteTransformKind.STUDY_GUIDE:
                instruction = "Create a study guide with concepts, questions, and review points."
            case NoteTransformKind.RELATED_IDEAS:
                instruction = "Develop related ideas grounded only in the selected notes."
            case unreachable:
                assert_never(unreachable)
        selected = "\n".join(
            f"Revision {revision.revision_id}: "
            + json.dumps(
                revision.content,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            for revision in revisions
        )
        payload: dict[str, object] = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "user": f"note-transform:{kind.value}",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Transform only the supplied immutable note revisions. Return JSON as "
                        '{"content":{"blocks":[...]}} with no markdown wrapper. '
                        + instruction
                    ),
                },
                {"role": "user", "content": selected},
            ],
        }
        with httpx.Client(
            base_url=self.base_url,
            timeout=120.0,
            transport=self.transport,
        ) as client:
            response = client.post("/chat/completions", json=payload)
            response.raise_for_status()
        envelope = _CompletionPayload.model_validate_json(response.text)
        if not envelope.choices:
            raise GroundingCompletionError("completion response contains no choices")
        try:
            transformed = _TransformPayload.model_validate_json(
                envelope.choices[0].message.content
            )
        except ValueError as error:
            raise GroundingCompletionError(
                "completion response is not a note transform contract"
            ) from error
        return transformed.content
