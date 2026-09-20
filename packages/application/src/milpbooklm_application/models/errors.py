"""Normalized provider failures and bounded retry policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ProviderErrorCode(StrEnum):
    """The complete provider error vocabulary from guide chapter 10."""

    INVALID_REQUEST = "invalid_request"
    CAPABILITY_MISMATCH = "capability_mismatch"
    AUTH = "auth"
    POLICY_DENIED = "policy_denied"
    QUOTA = "quota"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    TRANSPORT = "transport"
    PROVIDER_INTERNAL = "provider_internal"
    MALFORMED_RESPONSE = "malformed_response"
    SAFETY_REFUSAL = "safety_refusal"
    CANCELLED = "cancelled"
    UNCERTAIN_SUBMISSION = "uncertain_submission"


_RETRYABLE = frozenset(
    {
        ProviderErrorCode.RATE_LIMITED,
        ProviderErrorCode.TIMEOUT,
        ProviderErrorCode.TRANSPORT,
        ProviderErrorCode.PROVIDER_INTERNAL,
    }
)


@dataclass(frozen=True, slots=True)
class ProviderFailureError(Exception):
    """A provider failure with stable retry semantics and no raw provider content."""

    code: ProviderErrorCode
    message: str
    retry_after_seconds: float | None = None
    provider_correlation_id: str | None = None

    @property
    def retryable(self) -> bool:
        """Whether bounded retry may be considered for this failure."""
        return self.code in _RETRYABLE

    def __str__(self) -> str:
        """Render the normalized, content-free failure."""
        return f"{self.code.value}: {self.message}"


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Bounded exponential retry policy constrained by an operation deadline."""

    max_attempts: int = 3
    initial_delay_seconds: float = 0.25
    maximum_delay_seconds: float = 2.0

    def delay(self, *, attempt: int, now: datetime, deadline: datetime) -> float | None:
        """Return the next delay, or None when retry would exceed policy/deadline."""
        if attempt >= self.max_attempts:
            return None
        growth = pow(2.0, max(attempt - 1, 0))
        seconds = min(self.initial_delay_seconds * growth, self.maximum_delay_seconds)
        if now.timestamp() + seconds >= deadline.timestamp():
            return None
        return seconds
