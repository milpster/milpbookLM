"""
Hardened SSRF-pinned fetch service (ING-02b).

Only this transport may perform outbound HTTP for the platform.
"""

from .addressing import (
    SSRFBlockedError,
    classify_address,
    default_resolver,
    select_pinned_address,
)
from .pinned import PinnedFetchTransport, ValidatingNetworkBackend
from .service import FetchLimits, HardenedFetchService
from .urls import FetchPolicyError, FetchTarget, normalize_url

__all__ = [
    "FetchLimits",
    "FetchPolicyError",
    "FetchTarget",
    "HardenedFetchService",
    "PinnedFetchTransport",
    "SSRFBlockedError",
    "ValidatingNetworkBackend",
    "classify_address",
    "default_resolver",
    "normalize_url",
    "select_pinned_address",
]
