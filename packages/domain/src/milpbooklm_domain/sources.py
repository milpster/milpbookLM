"""
Source / SourceVersion invariants (ch05 §5, ARCH-05-003/004).

Source is the logical, mutable-metadata object (display title, availability, restriction
policy). SourceVersion is an immutable snapshot: bytes, upstream identity, checksum and
content never change after activation. A metadata edit (display title) returns a NEW
Source with version content untouched.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from enum import StrEnum


class SourceType(StrEnum):
    """Logical source types (ch06 ingestion families + connectors)."""

    PDF = "pdf"
    DOCX = "docx"
    PPTX = "pptx"
    XLSX = "xlsx"
    EPUB = "epub"
    WEB_URL = "web_url"
    YOUTUBE = "youtube"
    PLAIN_TEXT = "plain_text"
    MARKDOWN = "markdown"
    CSV = "csv"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    CONNECTOR = "connector"


class Availability(StrEnum):
    """ch05: at least active, stale/refresh-failed, inaccessible/revoked, deleted/tombstoned."""

    ACTIVE = "active"
    STALE = "stale"
    INACCESSIBLE_REVOKED = "inaccessible_revoked"
    DELETED_TOMBSTONED = "deleted_tombstoned"


@dataclass(frozen=True, slots=True)
class SourceVersion:
    """Immutable snapshot of a source's payload while it is retained."""

    id: uuid.UUID
    source_id: uuid.UUID
    version_number: int
    content_sha256: str
    original_blob_id: uuid.UUID | None
    activated: bool = False


@dataclass(frozen=True, slots=True)
class Source:
    """The logical source: mutable metadata, stable identity and upstream origin."""

    id: uuid.UUID
    notebook_id: uuid.UUID
    type: SourceType
    origin: str
    display_title: str
    availability: Availability = Availability.ACTIVE
    connector_config_id: uuid.UUID | None = None
    current_version_id: uuid.UUID | None = None
    restriction_policy: tuple[str, ...] = ()
    versions: tuple[SourceVersion, ...] = ()


def apply_display_title_edit(source: Source, title: str) -> Source:
    """
    Apply a metadata-only display title edit to a source.

    Never rewrites bytes, upstream identity, version content, or historical manifests
    (ARCH-05-003).
    """
    return replace(source, display_title=title)


def eligible_for_retrieval(source: Source) -> bool:
    """
    Check whether a source is eligible for retrieval.

    Losing connector access makes the source ineligible for NEW retrieval/generation
    (ARCH-05-004) - historical version metadata is preserved, not deleted.
    """
    return source.availability in (Availability.ACTIVE, Availability.STALE)


def losing_connector_access(source: Source) -> Source:
    """Revocation transition: availability flips, all versions survive."""
    return replace(source, availability=Availability.INACCESSIBLE_REVOKED)


def assert_version_unchanged(before: SourceVersion, after: SourceVersion) -> None:
    """Immutability check used by property tests: identity fields must be byte-identical."""
    if (
        before.content_sha256 != after.content_sha256
        or before.original_blob_id != after.original_blob_id
    ):
        raise AssertionError("SourceVersion content changed after activation")
