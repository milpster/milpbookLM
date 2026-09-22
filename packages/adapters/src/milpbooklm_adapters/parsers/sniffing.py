"""
Bounded byte-based media sniffing shared by quarantine and worker paths.

Declared rules (guide/06 adapter matrix): identification never consults
filenames, extensions, or client MIME. Decisions use only the first
``SNIFF_SAMPLE_BYTES`` of the payload so streaming quarantine identification
and the worker's blob re-identification agree by construction.
"""

from __future__ import annotations

import codecs
import csv
import re
from typing import Final

from milpbooklm_domain.acquisition import IdentifiedMedia

SNIFF_SAMPLE_BYTES: Final = 8192
_SNIFF_DIALECT_SAMPLE_BYTES: Final = 4096
_PDF_MAGIC: Final = b"%PDF-"
_ZIP_MAGIC: Final = b"PK\x03\x04"
# OOXML workbooks/documents/decks start with [Content_Types].xml followed by
# the family part prefixes; the member-name bytes appear in the first local
# file headers, well inside the sniff sample for real-world files.
_OFFICE_PART_MARKERS: Final = (
    (b"application/epub+zip", IdentifiedMedia.EPUB),
    (b"xl/", IdentifiedMedia.XLSX),
    (b"word/", IdentifiedMedia.DOCX),
    (b"ppt/", IdentifiedMedia.PPTX),
)
_PNG_MAGIC: Final = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC: Final = b"\xff\xd8\xff"
_GIF_MAGICS: Final = (b"GIF87a", b"GIF89a")
_RIFF_MAGIC: Final = b"RIFF"
_RIFF_TYPE_OFFSET: Final = 8
_RIFF_TYPE_END: Final = 12
_WEBP_TYPE: Final = b"WEBP"
_WAV_TYPE: Final = b"WAVE"
_BMP_MAGIC: Final = b"BM"
_MP3_MAGIC: Final = b"ID3"
_MP4_FTYPE_OFFSET: Final = 4
_MP4_TYPE: Final = b"ftyp"
_WEBM_MAGIC: Final = b"\x1a\x45\xdf\xa3"
_MP3_SYNC_MIN: Final = 3
_MP3_SYNC_BYTE: Final = 0xFF
_MP3_SYNC_MASK: Final = 0xE0

_MEDIA_MAGIC_TABLE: Final = (
    (_PNG_MAGIC, IdentifiedMedia.IMAGE_PNG),
    (_JPEG_MAGIC, IdentifiedMedia.IMAGE_JPEG),
    (b"GIF87a", IdentifiedMedia.IMAGE_GIF),
    (b"GIF89a", IdentifiedMedia.IMAGE_GIF),
    (_BMP_MAGIC, IdentifiedMedia.IMAGE_BMP),
    (_WEBM_MAGIC, IdentifiedMedia.VIDEO_WEBM),
    (_MP3_MAGIC, IdentifiedMedia.AUDIO_MP3),
)

_HEADING: Final = re.compile(r"^#{1,6}\s")
_LIST_ITEM: Final = re.compile(r"^\s*[-*+]\s|^\s*\d+\.\s")
_QUOTE: Final = re.compile(r"^>\s")
_FENCE: Final = re.compile(r"^```")
_TABLE_ROW: Final = re.compile(r"^\s*\|.*\|\s*$")
_MARKDOWN_MARKER_THRESHOLD: Final = 2
_MIN_CSV_LINES: Final = 2
_HTML_DOCUMENT: Final = re.compile(r"<(?:!doctype\s+html|html|head|body)\b", re.IGNORECASE)


def sniff_media_type(data: bytes) -> IdentifiedMedia | None:
    """Return the identified media family for a payload sample (or None)."""
    if not data:
        return None
    if data.startswith(_PDF_MAGIC):
        return IdentifiedMedia.PDF
    if data.startswith(_ZIP_MAGIC):
        return _sniff_office(data)
    media = _sniff_media_binary(data)
    if media is not None:
        return media
    return _sniff_text(data)


def _sniff_media_binary(data: bytes) -> IdentifiedMedia | None:
    """Identify image/audio/video families from their byte magics (bounded)."""
    for prefix, media in _MEDIA_MAGIC_TABLE:
        if data.startswith(prefix):
            return media
    riff = _sniff_riff(data)
    if riff is not None:
        return riff
    if len(data) >= _MP4_FTYPE_OFFSET + 4 and (
        data[_MP4_FTYPE_OFFSET : _MP4_FTYPE_OFFSET + 4] == _MP4_TYPE
    ):
        return IdentifiedMedia.VIDEO_MP4
    return _sniff_mp3_sync(data)


def _sniff_riff(data: bytes) -> IdentifiedMedia | None:
    """Distinguish RIFF-subtyped WEBP (image) from WAV (audio)."""
    if data.startswith(_RIFF_MAGIC) and len(data) >= _RIFF_TYPE_END:
        riff_type = data[_RIFF_TYPE_OFFSET : _RIFF_TYPE_END]
        if riff_type == _WEBP_TYPE:
            return IdentifiedMedia.IMAGE_WEBP
        if riff_type == _WAV_TYPE:
            return IdentifiedMedia.AUDIO_WAV
    return None


def _sniff_mp3_sync(data: bytes) -> IdentifiedMedia | None:
    """MPEG audio frame sync: 0xFF followed by a marker/reserved bit pattern."""
    if (
        len(data) >= _MP3_SYNC_MIN
        and data[0] == _MP3_SYNC_BYTE
        and (data[2] & _MP3_SYNC_MASK) == _MP3_SYNC_MASK
    ):
        return IdentifiedMedia.AUDIO_MP3
    return None


def _sniff_office(data: bytes) -> IdentifiedMedia | None:
    sample = data[:SNIFF_SAMPLE_BYTES]
    return next(
        (media for marker, media in _OFFICE_PART_MARKERS if marker in sample), None
    )


def _sniff_text(data: bytes) -> IdentifiedMedia | None:
    """Classify UTF-8/UTF-16 text bytes as Markdown, CSV, or plain text."""
    sample = data[:_SNIFF_DIALECT_SAMPLE_BYTES]
    if sample.startswith(b"\xff\xfe") or sample.startswith(b"\xfe\xff"):
        encoding = "utf-16"
    else:
        # UTF-16 without a BOM is not accepted; a NUL in the sample is binary.
        if b"\x00" in data[:512]:
            return None
        encoding = "utf-8"
    # An incremental decoder (final=False) tolerates a multi-byte character cut
    # at the sample boundary; genuinely invalid bytes still raise.
    try:
        text = codecs.getincrementaldecoder(encoding)("strict").decode(sample)
    except UnicodeDecodeError:
        return None
    media = IdentifiedMedia.TEXT
    if _HTML_DOCUMENT.search(text):
        media = IdentifiedMedia.HTML
    elif _markdown_score(text) >= _MARKDOWN_MARKER_THRESHOLD:
        media = IdentifiedMedia.MARKDOWN
    elif _looks_like_csv(text):
        media = IdentifiedMedia.CSV
    elif _markdown_score(text) >= 1:
        media = IdentifiedMedia.MARKDOWN
    return media


def _looks_like_csv(text: str) -> bool:
    """Detect a delimited row structure with a consistent delimiter."""
    sample = text[: _SNIFF_DIALECT_SAMPLE_BYTES // 2]
    lines = [line for line in sample.splitlines() if line.strip()]
    if len(lines) < _MIN_CSV_LINES:
        return False
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        return _tolerant_delimiter(lines) is not None
    delimiter = dialect.delimiter
    delimited = [line for line in lines if delimiter in line]
    return len(delimited) >= max(_MIN_CSV_LINES, len(lines) - 1)


def _tolerant_delimiter(lines: list[str]) -> str | None:
    """Fallback for dialects the Sniffer rejects (quoted delimiter fields)."""
    for delimiter in (",", ";", "\t", "|"):
        counts = [line.count(delimiter) for line in lines]
        if min(counts) >= 1 and max(counts) - min(counts) <= 1:
            return delimiter
    return None


def _markdown_score(text: str) -> int:
    """Count distinct structural Markdown marker families in the sample."""
    lines = text.splitlines()
    markers = 0
    if any(_HEADING.match(line) for line in lines):
        markers += 1
    if any(_LIST_ITEM.match(line) for line in lines):
        markers += 1
    if any(_QUOTE.match(line) for line in lines):
        markers += 1
    if any(_FENCE.match(line) for line in lines):
        markers += 1
    if any(_TABLE_ROW.match(line) for line in lines):
        markers += 1
    return markers
