"""Private Pydantic boundary models for OpenAI-compatible responses."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class UsagePayload(BaseModel):
    """Provider token accounting."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    prompt_tokens: int = 0
    completion_tokens: int = 0


class DeltaPayload(BaseModel):
    """Text, llama.cpp reasoning, and optional tool calls from one chunk."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    content: str | None = None
    reasoning_content: str | None = None


class ChoicePayload(BaseModel):
    """One streaming choice."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    delta: DeltaPayload = DeltaPayload()
    finish_reason: str | None = None


class ChatChunkPayload(BaseModel):
    """Validated OpenAI-compatible streaming chunk."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    id: str | None = None
    model: str | None = None
    choices: tuple[ChoicePayload, ...] = ()
    usage: UsagePayload | None = None


class ModelsPayload(BaseModel):
    """Validated response from the local models probe."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    data: tuple[ModelPayload, ...] = ()


class ModelPayload(BaseModel):
    """One model advertised by the endpoint."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    id: str


ModelsPayload.model_rebuild()
