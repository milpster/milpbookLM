"""
Immutable blob object invariants, reconciliation classifications, and the GC delay policy.

FND-06 (ch19 "blob integrity", ch21 backup/restore). A blob is content-addressed and
immutable once finalized: its final name derives from its validated SHA-256 digest, and
the digest + size recorded at finalization are the integrity contract checked on every
read and by the reconciliation scan. Missing or corrupt referenced content is an
integrity incident - it is never substituted with empty content.

Reconciliation is a pure classification over three artifact spaces (temporary files,
finalized files, ``blob_objects`` rows); it is non-destructive by definition. Physical
GC is a separate, intentionally invoked action that may delete only once a safety
delay - strictly longer than the maximum backup-copy window (ch21) - has elapsed since
finalization.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final

# ch21: RPO <= 24 hours bounds how old the newest usable backup copy can be, so the
# maximum backup-copy window is 24 hours. GC may never delete a finalized object a
# backup copy within that window could still need.
MAX_BACKUP_WINDOW: Final[timedelta] = timedelta(hours=24)


class BlobState(StrEnum):
    """Lifecycle states of a ``blob_objects`` row (the ch05 state check constraint)."""

    STAGING = "staging"
    FINALIZED = "finalized"
    PURGED = "purged"


@dataclass(frozen=True, slots=True)
class BlobObject:
    """One content-addressed blob record (the ``blob_objects`` row as a domain value)."""

    id: uuid.UUID
    content_sha256: str
    size_bytes: int
    storage_path: str
    state: BlobState
    content_type: str | None = None
    finalized_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class BlobReference:
    """One polymorphic content-bearing user of a blob (the ``blob_references`` row)."""

    id: uuid.UUID
    blob_id: uuid.UUID
    referrer_kind: str
    referrer_id: uuid.UUID
    created_at: datetime | None = None


class ReconciliationClass(StrEnum):
    """The three reconciliation classifications (ch19: reconciliation identifies...)."""

    # A temporary file left by an interrupted write; never referenced, never final.
    ORPHAN_TEMPORARY = "orphan_temporary"
    # A finalized object (on disk and/or as a record) with no live references.
    UNREFERENCED_FINAL = "unreferenced_final"
    # A referenced finalized blob whose bytes are absent or fail the integrity scan:
    # an integrity incident, never deletable, never read back as empty content.
    MISSING_REFERENCED = "missing_referenced"


@dataclass(frozen=True, slots=True)
class ReconciliationFinding:
    """One classification result (metadata only; no content crosses this value)."""

    kind: ReconciliationClass
    blob_id: uuid.UUID | None
    content_sha256: str | None
    storage_path: str | None
    # Age anchor for the GC safety delay: the record's finalized_at, the file's
    # mtime when the object has no record, or the temp's mtime for orphan
    # temporaries - an in-flight put keeps touching its temp, so a fresh temp
    # never ages out and can never be swept from under a live write.
    finalized_at: datetime | None
    # Whether the object's file is on disk right now. GC may only act on
    # file-present findings; a record without a file is already settled.
    file_present: bool
    detail: str


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    """The outcome of one non-destructive reconciliation scan (idempotent to repeat)."""

    at: datetime
    findings: tuple[ReconciliationFinding, ...]

    def findings_of(self, kind: ReconciliationClass) -> tuple[ReconciliationFinding, ...]:
        """Return the findings of one classification (empty when none)."""
        return tuple(finding for finding in self.findings if finding.kind is kind)


@dataclass(frozen=True, slots=True)
class GcReport:
    """The outcome of one intentionally invoked GC pass (never a side effect of a scan)."""

    at: datetime
    swept_temps: int
    deleted_finals: int
    pending_safety_delay: int
    integrity_incidents: int


def gc_safety_delay_valid(
    safety_delay: timedelta, max_backup_window: timedelta = MAX_BACKUP_WINDOW
) -> bool:
    """ch21: the GC safety delay must be STRICTLY longer than the max backup-copy window."""
    return safety_delay > max_backup_window


def gc_eligible(
    *, finalized_at: datetime | None, now: datetime, safety_delay: timedelta
) -> bool:
    """Return True once the finalization is at least the safety delay older than now."""
    if finalized_at is None:
        return False
    return now - finalized_at >= safety_delay
