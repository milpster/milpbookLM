"""OpenAI-compatible transport and the native local llama.cpp endpoint adapter."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, Protocol

import anyio
import httpx
from milpbooklm_application.credentials import CredentialRef, CredentialStore
from milpbooklm_application.models.contracts import (
    Accepted,
    Cancelled,
    ChatRequest,
    Completed,
    Delta,
    Failed,
    ProviderEvent,
    Refused,
    Usage,
)
from milpbooklm_application.models.errors import ProviderErrorCode, ProviderFailureError
from milpbooklm_application.models.registry import ProviderTrust
from milpbooklm_application.ports import AuditLog

from milpbooklm_adapters.models.openai_schema import (
    ChatChunkPayload,
    ChoicePayload,
    ModelsPayload,
)

BIG_PICKLE_NAME: Final = "Big Pickle"
MUSE_SPARK_STANDARD_NAME: Final = "Muse Spark Standard"
LLAMA_CPP_LOCAL_NAME: Final = "llama.cpp local"
LLAMA_CPP_BASE_URL: Final = "http://127.0.0.1:8009/v1"


class DisclosureRecorder(Protocol):
    """Durable metadata-only disclosure sink invoked before external transport."""

    def record_external_dispatch(
        self,
        *,
        actor_id: uuid.UUID,
        provider: str,
        model_role: str,
        operation_id: uuid.UUID,
        request_id: str,
    ) -> None:
        """Persist an external dispatch disclosure."""
        ...


class AuditDisclosureRecorder:
    """Persist external dispatch disclosure through the append-only audit port."""

    def __init__(self, audit: AuditLog) -> None:
        """Wire the durable audit sink."""
        self._audit = audit

    def record_external_dispatch(
        self,
        *,
        actor_id: uuid.UUID,
        provider: str,
        model_role: str,
        operation_id: uuid.UUID,
        request_id: str,
    ) -> None:
        """Commit metadata-only disclosure before the adapter resolves a secret."""
        self._audit.record(
            actor_id=actor_id,
            action="provider.external_dispatch_disclosed",
            subject_kind="model_operation",
            subject_id=operation_id,
            details={"provider": provider, "model_role": model_role},
            request_id=request_id,
        )


@dataclass(frozen=True, slots=True)
class OpenAIProviderConfig:
    """Installation-owned endpoint settings; credentials remain separate."""

    name: str
    base_url: str
    trust: ProviderTrust
    credential_ref: CredentialRef | None = None
    max_connections: int = 8


class OpenAICompatibleAdapter:
    """Provider-neutral chat adapter for OpenAI-compatible HTTP endpoints."""

    def __init__(
        self,
        config: OpenAIProviderConfig,
        credentials: CredentialStore | None = None,
        disclosure: DisclosureRecorder | None = None,
    ) -> None:
        """Wire installation config and dispatch-only secret/disclosure boundaries."""
        self._config = config
        self._credentials = credentials
        self._disclosure = disclosure

    async def chat(self, request: ChatRequest) -> AsyncIterator[ProviderEvent]:
        """Stream normalized events with monotonic sequence and usage before completion."""
        yield Accepted(seq=1, provider=self._config.name)
        try:
            async for event in self._dispatch(request):
                yield event
        except ProviderFailureError as failure:
            yield Failed(seq=2, code=failure.code, retryable=failure.retryable)
        except httpx.TimeoutException:
            yield Failed(seq=2, code=ProviderErrorCode.TIMEOUT, retryable=True)
        except httpx.TransportError:
            yield Failed(seq=2, code=ProviderErrorCode.TRANSPORT, retryable=True)
        except (ValueError, TypeError):
            yield Failed(seq=2, code=ProviderErrorCode.MALFORMED_RESPONSE, retryable=False)
        except anyio.get_cancelled_exc_class():
            yield Cancelled(seq=2)
            raise

    async def _dispatch(self, request: ChatRequest) -> AsyncIterator[ProviderEvent]:
        timeout_seconds = max(
            (request.envelope.deadline - datetime.now(tz=UTC)).total_seconds(),
            0.001,
        )
        timeout = httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 5.0))
        limits = httpx.Limits(
            max_connections=self._config.max_connections,
            max_keepalive_connections=self._config.max_connections,
        )
        async with (
            httpx.AsyncClient(
                base_url=self._config.base_url.rstrip("/"),
                headers=self._headers(request),
                timeout=timeout,
                limits=limits,
                follow_redirects=False,
            ) as client,
            client.stream(
                "POST", "/chat/completions", json=self._request_body(request)
            ) as response,
        ):
            if response.status_code >= httpx.codes.BAD_REQUEST:
                failure = await self._http_failure(response)
                yield Failed(
                    seq=2,
                    code=failure.code,
                    retryable=failure.retryable,
                    retry_after_seconds=failure.retry_after_seconds,
                )
                return
            async for event in self._stream_events(response):
                yield event

    @staticmethod
    async def _stream_events(response: httpx.Response) -> AsyncIterator[ProviderEvent]:
        seq = 2
        finish_reason = "stop"
        usage = UsagePayloadState()
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            payload = line.removeprefix("data: ")
            if payload == "[DONE]":
                break
            chunk = ChatChunkPayload.model_validate_json(payload)
            if chunk.usage is not None:
                usage = UsagePayloadState(
                    input_units=chunk.usage.prompt_tokens,
                    output_units=chunk.usage.completion_tokens,
                )
            for choice in chunk.choices:
                deltas = _choice_deltas(choice, seq)
                for delta in deltas:
                    yield delta
                seq += len(deltas)
                finish_reason = choice.finish_reason or finish_reason
        if finish_reason == "content_filter":
            yield Refused(seq=seq, reason="provider safety policy")
            return
        yield Usage(seq=seq, input_units=usage.input_units, output_units=usage.output_units)
        yield Completed(seq=seq + 1, finish_reason=finish_reason)

    def _headers(self, request: ChatRequest) -> dict[str, str]:
        if self._config.trust is ProviderTrust.EXTERNAL:
            if self._disclosure is None:
                raise ProviderFailureError(
                    ProviderErrorCode.POLICY_DENIED, "external disclosure sink missing"
                )
            self._disclosure.record_external_dispatch(
                actor_id=request.envelope.actor_user_id,
                provider=self._config.name,
                model_role=request.envelope.model_role.value,
                operation_id=request.envelope.operation_id,
                request_id=request.envelope.request_id,
            )
        headers = {"Accept": "text/event-stream", "Content-Type": "application/json"}
        if self._config.credential_ref is not None:
            if self._credentials is None:
                raise ProviderFailureError(ProviderErrorCode.AUTH, "credential store missing")
            if self._config.credential_ref.owner_user_id not in (
                None,
                request.envelope.actor_user_id,
            ):
                raise ProviderFailureError(
                    ProviderErrorCode.POLICY_DENIED, "credential ownership mismatch"
                )
            secret = self._credentials.dispatch(self._config.credential_ref)
            headers["Authorization"] = f"Bearer {secret.decode('utf-8')}"
        return headers

    @staticmethod
    def _request_body(request: ChatRequest) -> dict[str, object]:
        return {
            "model": request.model,
            "stream": True,
            "stream_options": {"include_usage": True},
            "messages": [{"role": item.role, "content": item.content} for item in request.messages],
        }

    @staticmethod
    async def _http_failure(response: httpx.Response) -> ProviderFailureError:
        retry_after = response.headers.get("retry-after")
        retry_seconds = float(retry_after) if retry_after and retry_after.isdigit() else None
        match response.status_code:
            case 400 | 404 | 422:
                code = ProviderErrorCode.INVALID_REQUEST
            case 408:
                code = ProviderErrorCode.TIMEOUT
            case 401 | 403:
                code = ProviderErrorCode.AUTH
            case 429:
                code = ProviderErrorCode.RATE_LIMITED
            case status if status >= httpx.codes.INTERNAL_SERVER_ERROR:
                code = ProviderErrorCode.PROVIDER_INTERNAL
            case _:
                code = ProviderErrorCode.TRANSPORT
        await response.aread()
        return ProviderFailureError(code, f"provider HTTP {response.status_code}", retry_seconds)


@dataclass(frozen=True, slots=True)
class UsagePayloadState:
    """Internal stream accounting accumulator."""

    input_units: int = 0
    output_units: int = 0


def _choice_deltas(choice: ChoicePayload, seq: int) -> tuple[Delta, ...]:
    events: list[Delta] = []
    if choice.delta.reasoning_content:
        events.append(Delta(seq=seq, text=choice.delta.reasoning_content, reasoning=True))
    if choice.delta.content:
        events.append(Delta(seq=seq + len(events), text=choice.delta.content))
    return tuple(events)


class LlamaCppAdapter(OpenAICompatibleAdapter):
    """Native local llama.cpp server adapter using its OpenAI-compatible surface."""

    def __init__(self, *, base_url: str = LLAMA_CPP_BASE_URL) -> None:
        """Configure the fixed loopback default without credentials or disclosure."""
        super().__init__(
            OpenAIProviderConfig(
                name=LLAMA_CPP_LOCAL_NAME,
                base_url=base_url,
                trust=ProviderTrust.LOCAL,
            )
        )

    async def probe_models(self) -> tuple[str, ...]:
        """Return model IDs advertised by the local server."""
        async with httpx.AsyncClient(base_url=self._config.base_url, timeout=2.0) as client:
            response = await client.get("/models")
            response.raise_for_status()
            payload = ModelsPayload.model_validate_json(response.text)
        return tuple(model.id for model in payload.data)
