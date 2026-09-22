"""
Web fetch port and web-URL acquisition (ING-02b, provider-shaped).

The fetch service is a durable infrastructure concern: ingestion (this module)
and the research runtime (ch11 ``web.fetch``) both consume the SAME port, so
SSRF/SSRF-pinning/cap policy lives in exactly one place.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Protocol

from milpbooklm_domain.acquisition import AcquisitionError, AcquisitionErrorCode

from .audit_actions import AuditAction
from .ports import AuditLog
from .source_acquisition import (
    AcquireSource,
    AcquireSourceCommand,
    SourceView,
    WebCaptureMetadata,
)

_FETCH_TO_ACQUISITION: Final = {
    "unsupported": AcquisitionErrorCode.UNSUPPORTED,
    "corrupt": AcquisitionErrorCode.CORRUPT,
    "too_large": AcquisitionErrorCode.TOO_LARGE,
    "timeout": AcquisitionErrorCode.TIMEOUT,
    "policy_blocked": AcquisitionErrorCode.POLICY_BLOCKED,
    "internal": AcquisitionErrorCode.INTERNAL,
}


class FetchErrorCode(StrEnum):
    """Stable fetch refusal classes (guide/06 failure semantics + guide/19)."""

    UNSUPPORTED = "unsupported"
    CORRUPT = "corrupt"
    TOO_LARGE = "too_large"
    TIMEOUT = "timeout"
    POLICY_BLOCKED = "policy_blocked"
    INTERNAL = "internal"


@dataclass(frozen=True, slots=True)
class WebFetchRefusedError(Exception):
    """A fetch was refused by policy, caps, or transport (no partial content)."""

    code: FetchErrorCode
    detail: str

    def __str__(self) -> str:
        """Return the stable code and safe detail."""
        return f"{self.code.value}: {self.detail}"


@dataclass(frozen=True, slots=True)
class WebFetchCommand:
    """One URL to fetch (untrusted input; validated at the service boundary)."""

    url: str


@dataclass(frozen=True, slots=True)
class WebFetchRecord:
    """The retrieval record: timestamp, chain, final URL, hash (guide/11)."""

    requested_url: str
    final_url: str
    captured_at: str
    status_code: int
    content_sha256: str
    size_bytes: int
    content_type: str
    redirect_chain: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FetchedWebContent:
    """Fetched bytes plus the retrieval record and final response headers."""

    body: bytes
    record: WebFetchRecord
    headers: tuple[tuple[str, str], ...]


class WebFetchPort(Protocol):
    """The dedicated fetch service; no unmodified convenience client may replace it."""

    async def fetch(self, command: WebFetchCommand) -> FetchedWebContent:
        """Fetch one URL with SSRF-pinned transport, caps, and full recording."""
        ...


@dataclass(frozen=True, slots=True)
class AcquireWebSourceCommand:
    """Trusted acquisition metadata paired with an untrusted URL."""

    notebook_id: uuid.UUID
    actor_id: uuid.UUID
    title: str
    url: str
    refresh_source_id: uuid.UUID | None = None


class AcquireWebSource:
    """Fetch a web URL through the dedicated service and acquire it as a source."""

    def __init__(
        self,
        *,
        fetch: WebFetchPort,
        acquire: AcquireSource,
        audit: AuditLog,
    ) -> None:
        """Wire the fetch port, the byte-acquisition use case, and the audit log."""
        self._fetch = fetch
        self._acquire = acquire
        self._audit = audit

    async def __call__(
        self, command: AcquireWebSourceCommand
    ) -> tuple[SourceView, bool, uuid.UUID]:
        """Fetch, then run the fetched bytes through quarantine/blob/parse."""
        try:
            fetched = await self._fetch.fetch(WebFetchCommand(url=command.url))
        except WebFetchRefusedError as exc:
            if command.refresh_source_id is not None:
                self._acquire.mark_refresh_failed(command.refresh_source_id, command.actor_id)
            self._audit.record(
                actor_id=command.actor_id,
                action=AuditAction.ACQUISITION_REJECTED.value,
                subject_kind="notebook",
                subject_id=command.notebook_id,
                details={"error_code": exc.code.value, "url": command.url},
            )
            raise AcquisitionError(
                _FETCH_TO_ACQUISITION[exc.code.value], exc.detail
            ) from exc
        capture = WebCaptureMetadata(
            requested_url=fetched.record.requested_url,
            final_url=fetched.record.final_url,
            captured_at=fetched.record.captured_at,
            status_code=fetched.record.status_code,
            content_sha256=fetched.record.content_sha256,
            content_type=fetched.record.content_type,
            redirect_chain=fetched.record.redirect_chain,
            headers=fetched.headers,
        )
        return await self._acquire(
            AcquireSourceCommand(
                notebook_id=command.notebook_id,
                actor_id=command.actor_id,
                display_title=command.title,
                origin_kind="web_url",
                web_capture=capture,
                refresh_source_id=command.refresh_source_id,
            ),
            _one_shot(fetched.body),
        )


async def _one_shot(data: bytes) -> AsyncIterator[bytes]:
    """Adapt fetched bytes to the streaming acquisition port."""
    yield data
