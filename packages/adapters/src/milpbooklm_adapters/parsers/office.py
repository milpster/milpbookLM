"""
Shared OOXML pre-flight: archive bounds and macro/external-reference policy.

Every office parser opens the archive through :func:`open_bounded_archive`
first. Declared limits: member count, per-member and total uncompressed
sizes (a zip bomb fails as ``too_large`` before any inflater runs over
unbounded output), and a bounded read cap per relationship part. Macros
(``vbaProject.bin`` under the family part prefix) and non-hyperlink
external references are policy rejections — never executed, never fetched.
"""

from __future__ import annotations

import io
import pathlib
import re
import zipfile
from typing import Final

MAX_ARCHIVE_MEMBERS: Final = 4_096
MAX_MEMBER_BYTES: Final = 64 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES: Final = 256 * 1024 * 1024
MAX_RELS_READ_BYTES: Final = 1024 * 1024

_VBA_PART: Final = "vbaProject.bin"
_HYPERLINK_SUFFIX: Final = "/hyperlink"
_RELATIONSHIP: Final = re.compile(rb"<Relationship\b[^>]*>")


class OfficeCorruptError(Exception):
    """The OOXML archive or a required part cannot be parsed."""


class OfficePolicyError(Exception):
    """The document violates an ingestion policy (macros, external references)."""


class OfficeTooLargeError(Exception):
    """The archive exceeds declared uncompressed/member limits."""


def open_bounded_archive(data: bytes) -> zipfile.ZipFile:
    """Open the OOXML zip with declared bomb limits enforced up front."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise OfficeCorruptError("office document is not a valid zip archive") from exc
    infos = archive.infolist()
    if len(infos) > MAX_ARCHIVE_MEMBERS:
        raise OfficeTooLargeError(f"archive exceeds {MAX_ARCHIVE_MEMBERS} member limit")
    total = 0
    for info in infos:
        member_path = pathlib.PurePosixPath(info.filename.replace("\\", "/"))
        if member_path.is_absolute() or ".." in member_path.parts:
            raise OfficePolicyError("archive contains an unsafe member path")
        if info.flag_bits & 0x1:
            raise OfficePolicyError("archive contains encrypted members")
        if info.file_size > MAX_MEMBER_BYTES:
            raise OfficeTooLargeError("archive member exceeds uncompressed size limit")
        total += info.file_size
    if total > MAX_TOTAL_UNCOMPRESSED_BYTES:
        raise OfficeTooLargeError("archive exceeds total uncompressed size limit")
    return archive


def assert_no_macros(archive: zipfile.ZipFile, family_prefix: str) -> None:
    """Reject macro-enabled office documents without loading any part."""
    macro_part = f"{family_prefix}{_VBA_PART}"
    if any(info.filename == macro_part for info in archive.infolist()):
        raise OfficePolicyError("office document contains macros")


def assert_no_external_references(archive: zipfile.ZipFile) -> None:
    """Reject non-hyperlink external relationships; hyperlinks stay inert text."""
    for info in archive.infolist():
        if not info.filename.endswith(".rels"):
            continue
        with archive.open(info) as handle:
            payload = handle.read(MAX_RELS_READ_BYTES + 1)
        if len(payload) > MAX_RELS_READ_BYTES:
            raise OfficeCorruptError("relationship part exceeds read limit")
        for relationship in _RELATIONSHIP.finditer(payload):
            attributes = relationship.group(0)
            if b'TargetMode="External"' not in attributes:
                continue
            match = re.search(rb'Type="([^"]+)"', attributes)
            relationship_type = match.group(1) if match else b""
            if not relationship_type.endswith(_HYPERLINK_SUFFIX.encode()):
                raise OfficePolicyError("office document contains external references")
