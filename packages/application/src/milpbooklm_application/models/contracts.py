"""Immutable provider request envelopes and normalized lifecycle events."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import NewType

from milpbooklm_application.models.errors import ProviderErrorCode

ProviderConfigId = NewType("ProviderConfigId", uuid.UUID)
OperationId = NewType("OperationId", uuid.UUID)
InputManifestHash = NewType("InputManifestHash", str)


class ModelRole(StrEnum):
    """Routing-significant model purposes."""

    CHAT = "chat"
    RESEARCH = "research"
    QUERY_REWRITE = "query_rewrite"
    RERANKER = "reranker"
    EMBEDDING = "embedding"
    VISION = "vision"
    STT = "stt"
    TTS = "tts"
    REALTIME_VOICE = "realtime_voice"
    IMAGE_GENERATION = "image_generation"
    VIDEO_GENERATION = "video_generation"
    FAST_BACKGROUND = "fast_background"


class Modality(StrEnum):
    """Provider input/output modalities used during negotiation."""

    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    EMBEDDING = "embedding"


class ContentClassification(StrEnum):
    """Bounded content trust classes used by routing policy."""

    PUBLIC = "public"
    INTERNAL = "internal"
    RESTRICTED = "restricted"


@dataclass(frozen=True, slots=True)
class ProviderRequestEnvelope:
    """Identity, policy and replay context shared by every model operation."""

    request_id: str
    operation_id: OperationId
    actor_user_id: uuid.UUID
    provider_config_id: ProviderConfigId | None
    model_role: ModelRole
    input_manifest_hash: InputManifestHash
    required_capabilities: frozenset[str]
    content_classification: ContentClassification
    deadline: datetime
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """One provider-neutral chat message."""

    role: str
    content: str


@dataclass(frozen=True, slots=True)
class ChatRequest:
    """Chat generation request."""

    envelope: ProviderRequestEnvelope
    messages: tuple[ChatMessage, ...]
    model: str
    stream: bool = True


@dataclass(frozen=True, slots=True)
class StructuredRequest:
    """JSON-schema constrained generation request."""

    envelope: ProviderRequestEnvelope
    messages: tuple[ChatMessage, ...]
    model: str
    json_schema: str


@dataclass(frozen=True, slots=True)
class TextBatchRequest:
    """Embedding or reranking request carrying direct operation input."""

    envelope: ProviderRequestEnvelope
    texts: tuple[str, ...]
    model: str
    query: str | None = None


@dataclass(frozen=True, slots=True)
class MediaRequest:
    """Image, speech or video request using immutable asset references."""

    envelope: ProviderRequestEnvelope
    prompt: str
    model: str
    input_asset_refs: tuple[str, ...] = ()
    output_mime_type: str | None = None


@dataclass(frozen=True, slots=True)
class Accepted:
    """Provider accepted the operation."""

    seq: int
    provider: str
    model_revision: str | None = None
    provider_correlation_id: str | None = None


@dataclass(frozen=True, slots=True)
class Delta:
    """One visible or reasoning stream delta."""

    seq: int
    text: str
    reasoning: bool = False


@dataclass(frozen=True, slots=True)
class ToolCall:
    """Normalized tool invocation emitted by a model."""

    seq: int
    call_id: str
    name: str
    arguments_json: str


@dataclass(frozen=True, slots=True)
class Usage:
    """Normalized token or unit accounting; emitted before completion."""

    seq: int
    input_units: int
    output_units: int


@dataclass(frozen=True, slots=True)
class Completed:
    """Terminal successful lifecycle event."""

    seq: int
    finish_reason: str
    result_ref: str | None = None


@dataclass(frozen=True, slots=True)
class Refused:
    """Terminal provider safety refusal."""

    seq: int
    reason: str


@dataclass(frozen=True, slots=True)
class Cancelled:
    """Terminal cooperative cancellation."""

    seq: int


@dataclass(frozen=True, slots=True)
class Failed:
    """Terminal normalized provider failure."""

    seq: int
    code: ProviderErrorCode
    retryable: bool
    retry_after_seconds: float | None = None


type ProviderEvent = Accepted | Delta | ToolCall | Usage | Completed | Refused | Cancelled | Failed
