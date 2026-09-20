"""Deterministic product fakes used by the offline/local-first prototype."""

from __future__ import annotations

from collections.abc import AsyncIterator
from enum import StrEnum

import anyio
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
from milpbooklm_application.models.errors import ProviderErrorCode


class FakeScenario(StrEnum):
    """Deterministic provider outcomes covering the prototype failure matrix."""

    SUCCESS = "success"
    QUOTA = "quota"
    REFUSAL = "refusal"
    TIMEOUT = "timeout"
    MALFORMED_STRUCTURED = "malformed_structured"
    STREAM_INTERRUPT = "stream_interrupt"
    CANCEL = "cancel"
    ASYNC_COMPLETION = "async_completion"


class FakeProvider:
    """A deterministic provider implementation that performs no external I/O."""

    def __init__(self, scenario: FakeScenario = FakeScenario.SUCCESS) -> None:
        """Select one stable outcome."""
        self._scenario = scenario

    async def chat(self, request: ChatRequest) -> AsyncIterator[ProviderEvent]:
        """Emit a contract-valid lifecycle for the selected scenario."""
        del request
        yield Accepted(seq=1, provider="deterministic-fake", model_revision="fake-v1")
        match self._scenario:
            case FakeScenario.SUCCESS:
                yield Delta(seq=2, text="prototype response")
                yield Usage(seq=3, input_units=4, output_units=2)
                yield Completed(seq=4, finish_reason="stop")
            case FakeScenario.QUOTA:
                yield Failed(seq=2, code=ProviderErrorCode.QUOTA, retryable=False)
            case FakeScenario.REFUSAL:
                yield Refused(seq=2, reason="safety policy")
            case FakeScenario.TIMEOUT:
                yield Failed(seq=2, code=ProviderErrorCode.TIMEOUT, retryable=True)
            case FakeScenario.MALFORMED_STRUCTURED:
                yield Failed(seq=2, code=ProviderErrorCode.MALFORMED_RESPONSE, retryable=False)
            case FakeScenario.STREAM_INTERRUPT:
                yield Delta(seq=2, text="partial")
                yield Failed(seq=3, code=ProviderErrorCode.TRANSPORT, retryable=True)
            case FakeScenario.CANCEL:
                yield Cancelled(seq=2)
            case FakeScenario.ASYNC_COMPLETION:
                await anyio.sleep(0)
                yield Usage(seq=2, input_units=1, output_units=1)
                yield Completed(seq=3, finish_reason="async_completed", result_ref="fake://result")
