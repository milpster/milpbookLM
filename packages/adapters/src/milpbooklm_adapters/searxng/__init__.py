"""
SearXNG adapter package (RSR-01a): service, engine pin, and CI fake.

Deployment contract: pinned image, private networks, ``formats: [html, json]``
explicitly enabled, limiter OFF and no Valkey (D7 minimal profile) — see
infra/podman/searxng/ and infra/podman/versions.lock.
"""

from .fake import DEFAULT_CONFIG_ENGINES, FakeEngineConfig, FakeSearchResult, FakeSearxng
from .service import SEARXNG_VERSION, SearxngSearchService

__all__ = [
    "DEFAULT_CONFIG_ENGINES",
    "SEARXNG_VERSION",
    "FakeEngineConfig",
    "FakeSearchResult",
    "FakeSearxng",
    "SearxngSearchService",
]
