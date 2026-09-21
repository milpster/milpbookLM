"""Pure acquisition identities and stable rejection classes (ING-01a)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class IdentifiedMedia(StrEnum):
    """Media families identified from bytes, never client metadata."""

    PDF = "application/pdf"
    TEXT = "text/plain"
    MARKDOWN = "text/markdown"
    CSV = "text/csv"
    XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


class AcquisitionErrorCode(StrEnum):
    """Stable acquisition rejection classes exposed by the API."""

    UNSUPPORTED = "unsupported"
    CORRUPT = "corrupt"
    TOO_LARGE = "too_large"
    POLICY_BLOCKED = "policy_blocked"


@dataclass(frozen=True, slots=True)
class AcquisitionError(Exception):
    """A safe, stable acquisition rejection without client-controlled detail."""

    code: AcquisitionErrorCode
    detail: str

    def __str__(self) -> str:
        """Return the stable code and safe detail."""
        return f"{self.code.value}: {self.detail}"
