"""Public-video URL import (ING-02c 23.4): compliant-adapter-only, honest state.

Oracle: with the REFERENCE-DEPENDENCIES matrix naming no credential-free
compliant adapter, a public-video import terminates in the explicit
``transcript_unavailable`` source-version state — the attempt is recorded,
no transcript is fabricated, and no media is downloaded.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from milpbooklm_application.provenance import EffectiveRestrictions
from milpbooklm_application.public_video import (
    NO_COMPLIANT_ADAPTER,
    TRANSCRIPT_UNAVAILABLE,
    AcquirePublicVideo,
    PublicVideoCommand,
)
from milpbooklm_application.source_acquisition import (
    AcquireSourceCommand,
    SourceGuideView,
    SourceView,
)
from milpbooklm_domain.blobs import BlobObject
from milpbooklm_domain.sources import Availability, SourceType


@dataclass
class FakeCatalog:
    """In-memory SourceCatalog double recording every acquisition call."""

    calls: list[AcquireSourceCommand] = field(default_factory=list)
    unavailable_calls: list[tuple[AcquireSourceCommand, str, SourceType, str]] = field(
        default_factory=list
    )
    blob_calls: list[BlobObject] = field(default_factory=list)

    def acquire(self, command: AcquireSourceCommand, blob: BlobObject) -> tuple[SourceView, bool]:
        self.blob_calls.append(blob)
        self.calls.append(command)
        return _view(command), True

    def acquire_unavailable(
        self,
        command: AcquireSourceCommand,
        *,
        origin: str,
        source_type: SourceType,
        reason: str,
    ) -> tuple[SourceView, bool]:
        self.unavailable_calls.append((command, origin, source_type, reason))
        return _view(command), True

    def get(self, source_id: uuid.UUID, actor_id: uuid.UUID) -> SourceView | None:
        return None

    def rename(
        self, source_id: uuid.UUID, actor_id: uuid.UUID, title: str, etag: str
    ) -> SourceView:
        raise NotImplementedError

    def activate(self, source_id: uuid.UUID, actor_id: uuid.UUID) -> bool:
        return False

    def active_document_id(self, source_id: uuid.UUID, actor_id: uuid.UUID) -> uuid.UUID | None:
        return None

    def guide(
        self, source_id: uuid.UUID, actor_id: uuid.UUID
    ) -> SourceGuideView | None:
        return None

    def effective_restrictions(
        self, source_id: uuid.UUID, actor_id: uuid.UUID
    ) -> EffectiveRestrictions:
        raise NotImplementedError

    def set_selected(
        self, source_id: uuid.UUID, actor_id: uuid.UUID, *, selected: bool
    ) -> SourceView:
        raise NotImplementedError


@dataclass
class FakeAudit:
    actions: list[str] = field(default_factory=list)
    details: list[dict[str, str]] = field(default_factory=list)

    def record(
        self,
        *,
        actor_id: uuid.UUID | None,
        action: str,
        subject_kind: str | None = None,
        subject_id: uuid.UUID | None = None,
        details: dict[str, str] | None = None,
        request_id: str | None = None,
    ) -> None:
        self.actions.append(action)
        if details is not None:
            self.details.append(details)


class RecordingAdapter:
    """A compliant adapter double that records every URL it is asked for."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    def transcript(self, url: str) -> str | None:
        self.asked.append(url)
        return None


def _view(command: AcquireSourceCommand) -> SourceView:
    return SourceView(
        source_id=uuid.uuid4(),
        source_version_id=uuid.uuid4(),
        notebook_id=command.notebook_id,
        source_type=SourceType.YOUTUBE,
        display_title=command.display_title,
        availability=Availability.ACTIVE,
        content_sha256="0" * 64,
        content_size_bytes=0,
        version_status="parse_failed",
        etag="0",
        blob_id=uuid.uuid4(),
    )


def _command(url: str = "https://www.youtube.com/watch?v=abc123") -> PublicVideoCommand:
    return PublicVideoCommand(
        notebook_id=uuid.uuid4(),
        actor_id=uuid.uuid4(),
        title="Public video",
        url=url,
    )


def test_import_without_adapters_persists_explicit_unavailable_state() -> None:
    catalog = FakeCatalog()
    audit = FakeAudit()
    use_case = AcquirePublicVideo(catalog=catalog, audit=audit)

    outcome = use_case(_command())

    assert outcome.state == TRANSCRIPT_UNAVAILABLE
    assert outcome.reason == NO_COMPLIANT_ADAPTER
    assert outcome.attempted_adapters == 0
    assert outcome.view.version_status == "parse_failed"
    assert len(catalog.unavailable_calls) == 1
    assert catalog.blob_calls == []
    _, origin, source_type, reason = catalog.unavailable_calls[0]
    assert origin.startswith("public_video:https://")
    assert source_type is SourceType.YOUTUBE
    assert reason.startswith(TRANSCRIPT_UNAVAILABLE)
    assert audit.actions == ["source.acquisition.succeeded"]
    assert audit.details[0]["transcript_state"] == TRANSCRIPT_UNAVAILABLE


def test_no_transcript_is_fabricated_and_no_bytes_are_downloaded() -> None:
    catalog = FakeCatalog()
    audit = FakeAudit()
    adapter = RecordingAdapter()
    use_case = AcquirePublicVideo(catalog=catalog, audit=audit, adapters=(adapter,))

    outcome = use_case(_command())

    assert adapter.asked == [_command().url]
    assert outcome.state == TRANSCRIPT_UNAVAILABLE
    assert outcome.view.version_status == "parse_failed"
    assert catalog.blob_calls == []


def test_unsafe_urls_are_rejected_before_persistence() -> None:
    catalog = FakeCatalog()
    audit = FakeAudit()
    use_case = AcquirePublicVideo(catalog=catalog, audit=audit)
    unsafe_urls = (
        "file:///etc/passwd",
        "ftp://example.com/video",
        "https://user:secret@example.com/watch?v=x",
        "https://example.com:8443/watch?v=x",
    )
    for url in unsafe_urls:
        try:
            use_case(_command(url))
            raise AssertionError(f"{url} was not rejected")
        except ValueError:
            pass

    assert catalog.unavailable_calls == []
    assert catalog.blob_calls == []
    assert len(audit.details) == len(unsafe_urls)
    assert all(entry["error_code"] == "url_rejected" for entry in audit.details)


def test_repeated_import_is_idempotent_on_the_origin() -> None:
    catalog = FakeCatalog()
    audit = FakeAudit()
    use_case = AcquirePublicVideo(catalog=catalog, audit=audit)

    outcome = use_case(_command())
    assert outcome.created is True
    assert (
        catalog.unavailable_calls[0][0].origin_kind == "public_video"
    )
