"""
Public-video URL acquisition (ING-02c sub-scope 23.4, guide/06).

Public-video imports accept a transcript and metadata ONLY through a
compliant adapter: no access-control bypass, no protected-media download,
no promised transcript where none is lawfully available. The REFERENCE-
DEPENDENCIES matrix names no credential-free compliant adapter, so a
deployed adapter set defaults to empty and every import terminates in the
explicit ``transcript_unavailable`` source-version state — the attempt is
recorded, never fabricated.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Final, Protocol
from urllib.parse import urlsplit

from milpbooklm_domain.sources import SourceType

from .audit_actions import AuditAction
from .ports import AuditLog
from .source_acquisition import AcquireSourceCommand, SourceCatalog, SourceView

TRANSCRIPT_UNAVAILABLE: Final = "transcript_unavailable"
NO_COMPLIANT_ADAPTER: Final = "no_compliant_adapter_without_credentials"
_URL_REJECTED: Final = "url_rejected"


class PublicVideoTranscriptAdapter(Protocol):
    """A lawfully compliant transcript source for one public video URL."""

    def transcript(self, url: str) -> str | None:
        """Return transcript text lawfully available for the URL, else None."""
        ...


@dataclass(frozen=True, slots=True)
class PublicVideoCommand:
    """One public-video URL import request (untrusted input)."""

    notebook_id: uuid.UUID
    actor_id: uuid.UUID
    title: str
    url: str


@dataclass(frozen=True, slots=True)
class PublicVideoOutcome:
    """The explicit import outcome: a source version plus its stable state."""

    view: SourceView
    created: bool
    state: str
    reason: str
    attempted_adapters: int


class AcquirePublicVideo:
    """Validate the URL, attempt compliant adapters, persist the explicit state."""

    def __init__(
        self,
        catalog: SourceCatalog,
        audit: AuditLog,
        adapters: tuple[PublicVideoTranscriptAdapter, ...] = (),
    ) -> None:
        """Wire the catalog, audit log, and the (possibly empty) adapter set."""
        self._catalog = catalog
        self._audit = audit
        self._adapters = adapters

    def __call__(self, command: PublicVideoCommand) -> PublicVideoOutcome:
        """Import one public-video URL into an explicit source-version state."""
        rejection = _reject_unsafe_url(command.url)
        if rejection is not None:
            self._audit.record(
                actor_id=command.actor_id,
                action=AuditAction.ACQUISITION_REJECTED.value,
                subject_kind="notebook",
                subject_id=command.notebook_id,
                details={"error_code": _URL_REJECTED, "reason": rejection},
            )
            raise ValueError(rejection)
        transcript = None
        for adapter in self._adapters:
            transcript = adapter.transcript(command.url)
            if transcript is not None:
                break
        view, created = self._catalog.acquire_unavailable(
            command=AcquireSourceCommand(
                notebook_id=command.notebook_id,
                actor_id=command.actor_id,
                display_title=command.title,
                origin_kind="public_video",
            ),
            origin=f"public_video:{command.url}",
            source_type=SourceType.YOUTUBE,
            reason=f"{TRANSCRIPT_UNAVAILABLE}:{NO_COMPLIANT_ADAPTER}",
        )
        self._audit.record(
            actor_id=command.actor_id,
            action=AuditAction.ACQUISITION_SUCCEEDED.value,
            subject_kind="source_version",
            subject_id=view.source_version_id,
            details={
                "media_type": "public_video_url",
                "transcript_state": TRANSCRIPT_UNAVAILABLE,
                "attempted_adapters": str(len(self._adapters)),
                "deduplicated": str(not created).lower(),
            },
        )
        return PublicVideoOutcome(
            view=view,
            created=created,
            state=TRANSCRIPT_UNAVAILABLE,
            reason=NO_COMPLIANT_ADAPTER,
            attempted_adapters=len(self._adapters),
        )


def _reject_unsafe_url(url: str) -> str | None:
    """Allow only plain public http(s) URLs without embedded credentials."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return "url scheme must be http or https"
    if parts.username is not None or parts.password is not None:
        return "embedded credentials are not accepted"
    if not parts.netloc:
        return "url has no host"
    if parts.port is not None and parts.port not in (80, 443):
        return "non-standard ports are not accepted"
    return None
