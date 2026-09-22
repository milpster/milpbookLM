"""Acquisition use cases and ports for quarantined text/PDF sources."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

from milpbooklm_domain.acquisition import AcquisitionError, IdentifiedMedia
from milpbooklm_domain.blobs import BlobObject
from milpbooklm_domain.job_capacity import CapacityClass
from milpbooklm_domain.jobs import JobRecord
from milpbooklm_domain.sources import Availability, SourceType
from milpbooklm_domain.telemetry import current_context

from .audit_actions import AuditAction
from .blob_store import BlobContentMismatchError, BlobStore
from .job_actor import InitiatingActor
from .job_usecases import JobPayload, JobPorts
from .ports import AuditLog
from .provenance import EffectiveRestrictions

IMPORTER_VERSION: Final = "ing-01a-v1"


@dataclass(frozen=True, slots=True)
class QuarantinedPayload:
    """A validated quarantine file identified solely from its bytes."""

    path: Path
    content_sha256: str
    size_bytes: int
    media: IdentifiedMedia


@dataclass(frozen=True, slots=True)
class SourceView:
    """Source plus its acquisition-stage version for API presentation."""

    source_id: uuid.UUID
    source_version_id: uuid.UUID
    notebook_id: uuid.UUID
    source_type: SourceType
    display_title: str
    availability: Availability
    content_sha256: str
    content_size_bytes: int
    version_status: str
    etag: str
    blob_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class SourceGuideView:
    """Deterministic phase-one guide derived from persisted source metadata."""

    source_id: uuid.UUID
    source_version_id: uuid.UUID
    summary: str
    labels: tuple[str, ...]
    restrictions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WebCaptureMetadata:
    """Immutable retrieval metadata carried into canonical web locators."""

    requested_url: str
    final_url: str
    captured_at: str
    status_code: int
    content_sha256: str
    content_type: str
    redirect_chain: tuple[str, ...]
    headers: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class AcquireSourceCommand:
    """Trusted command metadata paired with an untrusted byte stream."""

    notebook_id: uuid.UUID
    actor_id: uuid.UUID
    display_title: str
    origin_kind: str
    web_capture: WebCaptureMetadata | None = None


class QuarantineStore(Protocol):
    """Adapter-owned quarantine area; no final object is exposed before identify."""

    async def acquire(self, chunks: AsyncIterable[bytes]) -> QuarantinedPayload:
        """Stream, limit, hash, and identify one payload."""
        ...

    def chunks(self, payload: QuarantinedPayload) -> Iterable[bytes]:
        """Read validated bytes in bounded chunks for blob finalization."""
        ...

    def discard(self, payload: QuarantinedPayload) -> None:
        """Remove the quarantine file durably."""
        ...


class SourceCatalog(Protocol):
    """Ownership-scoped source persistence over the FND-03 tables."""

    def acquire(self, command: AcquireSourceCommand, blob: BlobObject) -> tuple[SourceView, bool]:
        """Create or return the idempotent source version."""
        ...

    def get(self, source_id: uuid.UUID, actor_id: uuid.UUID) -> SourceView | None:
        """Return one membership-visible source."""
        ...

    def rename(
        self, source_id: uuid.UUID, actor_id: uuid.UUID, title: str, etag: str
    ) -> SourceView:
        """CAS-update display metadata without touching source bytes."""
        ...

    def activate(self, source_id: uuid.UUID, actor_id: uuid.UUID) -> bool:
        """Atomically promote one parsed version with its canonical document."""
        ...

    def active_document_id(self, source_id: uuid.UUID, actor_id: uuid.UUID) -> uuid.UUID | None:
        """Return the active canonical document id of an activated source (or None)."""
        ...

    def guide(self, source_id: uuid.UUID, actor_id: uuid.UUID) -> SourceGuideView | None:
        """Return the phase-one deterministic Source Guide for an active source."""
        ...

    def effective_restrictions(
        self, source_id: uuid.UUID, actor_id: uuid.UUID
    ) -> EffectiveRestrictions:
        """Effective deny/reuse/export state across content-bearing ancestors."""
        ...

    def set_selected(
        self, source_id: uuid.UUID, actor_id: uuid.UUID, *, selected: bool
    ) -> SourceView:
        """Select or remove a source without purging retained bytes."""
        ...


class SourceNotFoundError(LookupError):
    """The source is absent or outside the actor's notebook memberships."""


class SourceConflictError(RuntimeError):
    """A metadata update lost its ETag compare-and-swap."""


class AcquireSource:
    """Quarantine, identify, content-address, persist, audit, and publish a completed job."""

    def __init__(
        self,
        *,
        quarantine: QuarantineStore,
        blobs: BlobStore,
        catalog: SourceCatalog,
        audit: AuditLog,
        jobs: JobPorts,
    ) -> None:
        """Wire the existing blob, audit, job, and source persistence seams."""
        self._quarantine = quarantine
        self._blobs = blobs
        self._catalog = catalog
        self._audit = audit
        self._jobs = jobs

    async def __call__(
        self, command: AcquireSourceCommand, chunks: AsyncIterable[bytes]
    ) -> tuple[SourceView, bool, uuid.UUID]:
        """Acquire bytes and return (source version, created, observable job id)."""
        try:
            payload = await self._quarantine.acquire(chunks)
        except AcquisitionError as exc:
            self._audit.record(
                actor_id=command.actor_id,
                action=AuditAction.ACQUISITION_REJECTED.value,
                subject_kind="notebook",
                subject_id=command.notebook_id,
                details={"error_code": exc.code.value},
            )
            raise
        try:
            blob = self._blobs.put(
                self._quarantine.chunks(payload), content_type=payload.media.value
            )
            if (
                blob.content_sha256 != payload.content_sha256
                or blob.size_bytes != payload.size_bytes
            ):
                raise BlobContentMismatchError(
                    "quarantine content changed between identification and finalization"
                )
            view, created = self._catalog.acquire(command, blob)
        finally:
            self._quarantine.discard(payload)
        job = self._publish_job(command, view)
        self._audit.record(
            actor_id=command.actor_id,
            action=AuditAction.ACQUISITION_SUCCEEDED.value,
            subject_kind="source_version",
            subject_id=view.source_version_id,
            details={"media_type": payload.media.value, "deduplicated": str(not created).lower()},
        )
        return view, created, job.id

    def _publish_job(self, command: AcquireSourceCommand, view: SourceView) -> JobRecord:
        context = current_context()
        actor = InitiatingActor(
            user_id=command.actor_id,
            request_id=context.request_id if context is not None else None,
            trace_id=context.trace_id if context is not None else None,
        )
        payload: JobPayload = {
            "source_id": str(view.source_id),
            "source_version_id": str(view.source_version_id),
            "blob_id": str(view.blob_id),
            "content_sha256": view.content_sha256,
            "importer_version": IMPORTER_VERSION,
        }
        if command.web_capture is not None:
            payload["web_final_url"] = command.web_capture.final_url
            payload["web_captured_at"] = command.web_capture.captured_at
            payload["web_capture"] = {
                "requested_url": command.web_capture.requested_url,
                "final_url": command.web_capture.final_url,
                "captured_at": command.web_capture.captured_at,
                "status_code": command.web_capture.status_code,
                "content_sha256": command.web_capture.content_sha256,
                "content_type": command.web_capture.content_type,
                "redirect_chain": list(command.web_capture.redirect_chain),
                "headers": [list(header) for header in command.web_capture.headers],
            }
        parse_job, _ = self._jobs.enqueue(
            kind="ingestion.parse",
            payload=payload,
            actor=actor,
            capacity_class=CapacityClass.INGESTION_INDEXING,
            notebook_id=command.notebook_id,
            capability="source_mutate",
            idempotency_key=f"parse:{view.source_version_id}:canonical-v1",
        )
        return parse_job
