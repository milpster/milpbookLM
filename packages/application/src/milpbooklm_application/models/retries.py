"""Bounded retry dispatch over normalized provider lifecycle events."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime

from milpbooklm_application.models.contracts import (
    Accepted,
    Cancelled,
    ChatRequest,
    Completed,
    Delta,
    Failed,
    ProviderEvent,
    Refused,
    ToolCall,
    Usage,
)
from milpbooklm_application.models.errors import ProviderErrorCode, RetryPolicy
from milpbooklm_application.models.ports import ChatProvider


class BoundedChatDispatcher:
    """
    Retry provider chat attempts within a bounded policy and the operation deadline.

    A retry is attempted only while no visible delta has been emitted: after visible
    output a retry would restart the stream and concatenate providers, which the
    fallback policy forbids - visible output is always terminal. A stream that ends
    without a terminal event is classified as a transport defect so the same bounded
    policy (and only it) decides whether to restart.
    """

    def __init__(
        self,
        policy: RetryPolicy,
        sleep: Callable[[float], Awaitable[None]],
    ) -> None:
        """Wire the retry policy and the sleep the backoff waits on."""
        self._policy = policy
        self._sleep = sleep

    async def dispatch(
        self, provider: ChatProvider, request: ChatRequest
    ) -> AsyncIterator[ProviderEvent]:
        """Stream the provider's events, restarting whole attempts within the bound."""
        attempt = 1
        while True:
            visible = False
            retried = False
            async for event in provider.chat(request):
                match event:
                    case Delta():
                        visible = True
                        yield event
                    case Failed() as failure if failure.retryable and not visible:
                        delay = self._retry_delay(attempt, request)
                        if delay is not None:
                            attempt += 1
                            retried = True
                            await self._sleep(delay)
                            break
                        yield event
                        return
                    case Completed() | Refused() | Cancelled() | Failed():
                        yield event
                        return
                    case Accepted() | ToolCall() | Usage():
                        yield event
                    case unreachable:
                        raise TypeError(f"unknown provider event: {unreachable!r}")
            if retried:
                continue
            # The provider ended without a terminal event (contract violation).
            failure = Failed(seq=2, code=ProviderErrorCode.TRANSPORT, retryable=True)
            delay = self._retry_delay(attempt, request)
            if delay is not None:
                attempt += 1
                await self._sleep(delay)
                continue
            yield failure
            return

    def _retry_delay(self, attempt: int, request: ChatRequest) -> float | None:
        """Return the next backoff for this attempt, or None when the bound is exhausted."""
        return self._policy.delay(
            attempt=attempt,
            now=datetime.now(tz=UTC),
            deadline=request.envelope.deadline,
        )
