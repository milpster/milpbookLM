"""Narrow async provider ports with no vendor SDK types."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from milpbooklm_application.models.contracts import (
    ChatRequest,
    MediaRequest,
    ProviderEvent,
    StructuredRequest,
    TextBatchRequest,
)


class ChatProvider(Protocol):
    """Streaming chat completion provider."""

    def chat(self, request: ChatRequest) -> AsyncIterator[ProviderEvent]:
        """Stream normalized chat lifecycle events."""
        ...


class StructuredGenerationProvider(Protocol):
    """Structured generation provider."""

    def generate_structured(self, request: StructuredRequest) -> AsyncIterator[ProviderEvent]:
        """Stream normalized structured-generation lifecycle events."""
        ...


class EmbeddingProvider(Protocol):
    """Embedding provider."""

    def embed(self, request: TextBatchRequest) -> AsyncIterator[ProviderEvent]:
        """Stream normalized embedding lifecycle events."""
        ...


class RerankerProvider(Protocol):
    """Reranking provider."""

    def rerank(self, request: TextBatchRequest) -> AsyncIterator[ProviderEvent]:
        """Stream normalized reranking lifecycle events."""
        ...


class ImageProvider(Protocol):
    """Image generation provider."""

    def generate_image(self, request: MediaRequest) -> AsyncIterator[ProviderEvent]:
        """Stream normalized image-generation lifecycle events."""
        ...


class TextToSpeechProvider(Protocol):
    """Text-to-speech provider."""

    def synthesize(self, request: MediaRequest) -> AsyncIterator[ProviderEvent]:
        """Stream normalized synthesis lifecycle events."""
        ...


class SpeechToTextProvider(Protocol):
    """Speech-to-text provider."""

    def transcribe(self, request: MediaRequest) -> AsyncIterator[ProviderEvent]:
        """Stream normalized transcription lifecycle events."""
        ...


class VideoProvider(Protocol):
    """Video generation provider."""

    def generate_video(self, request: MediaRequest) -> AsyncIterator[ProviderEvent]:
        """Stream normalized video-generation lifecycle events."""
        ...


@dataclass(frozen=True, slots=True)
class RealtimeFrame:
    """One typed frame on a provider-neutral duplex session."""

    seq: int
    mime_type: str
    payload: bytes


class RealtimeDuplexSession(Protocol):
    """Contract-only long-lived realtime session."""

    async def send(self, frame: RealtimeFrame) -> None:
        """Send one input frame."""
        ...

    def receive(self) -> AsyncIterator[RealtimeFrame]:
        """Receive output frames until the session closes."""
        ...

    async def close(self) -> None:
        """Close the duplex session."""
        ...


@dataclass(frozen=True, slots=True)
class RemoteMediaOperation:
    """Persistable identity and polling state for remote media work."""

    local_job_id: uuid.UUID
    provider_operation_id: str
    input_manifest_hash: str
    provider_config_id: uuid.UUID
    owner_user_id: uuid.UUID | None
    next_poll_at: datetime
    expires_at: datetime
    authoritative_state: str


class RemoteMediaOperations(Protocol):
    """Contract-only remote operation persistence and webhook replay seam."""

    async def save(self, operation: RemoteMediaOperation) -> None:
        """Persist the latest authoritative remote state."""
        ...

    async def observe(self, operation_id: str) -> AsyncIterator[ProviderEvent]:
        """Poll and stream normalized operation events."""
        ...

    async def accept_webhook(self, body: bytes, signature: str, replay_key: str) -> None:
        """Authenticate and apply a replay-protected callback."""
        ...

    async def cancel(self, operation_id: str) -> None:
        """Request best-effort remote cancellation."""
        ...
