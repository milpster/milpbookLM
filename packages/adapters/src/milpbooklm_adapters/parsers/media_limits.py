"""
Declared media parsing limits and typed media parser errors (ING-02c).

Image bounds are enforced from the header BEFORE any pixel decode; audio/video
containers are bounded by duration, track count, and a container allowlist.
Every violation is a typed error the child maps to an explicit source-version
state (too_large / corrupt / unsupported / no_content) — never success-empty.
"""

from __future__ import annotations

from typing import Final

# --- Images (enforced pre-decode, REFERENCE-DEPENDENCIES Images/OCR row) ---
MAX_IMAGE_PIXELS: Final = 64_000_000
MAX_IMAGE_DIMENSION: Final = 32_768
MAX_OCR_OUTPUT_BYTES: Final = 1_000_000
MAX_OCR_TIMEOUT_SECONDS: Final = 15
OCR_LANGUAGES: Final = "deu+eng"

# --- Audio/video (REFERENCE-DEPENDENCIES Audio/video row) ---
MAX_MEDIA_DURATION_MS: Final = 6 * 3_600_000
MAX_MEDIA_TRACKS: Final = 16
MAX_MEDIA_TOOL_OUTPUT_BYTES: Final = 1_000_000
MAX_MEDIA_TOOL_TIMEOUT_SECONDS: Final = 10
# ffprobe format_name strings (comma-joined demuxer aliases) for the accepted families.
ALLOWED_MEDIA_CONTAINERS: Final = frozenset(
    {"wav", "mp3", "mov,mp4,m4a,3gp,3g2,mj2", "matroska,webm"}
)


class MediaParseError(Exception):
    """Base class for typed media parser rejections."""


class ImageCorruptError(MediaParseError):
    """The image header or body cannot be decoded."""


class ImageTooLargeError(MediaParseError):
    """The image exceeds declared dimension or pixel limits (pre-decode)."""


class MediaCorruptError(MediaParseError):
    """The audio/video container cannot be probed."""


class MediaTooLargeError(MediaParseError):
    """The media exceeds declared duration or track limits."""


class MediaUnsupportedError(MediaParseError):
    """The media container is outside the ingestion allowlist."""


class OcrEmptyError(MediaParseError):
    """OCR ran cleanly but produced no text (explicit no-content state)."""
