"""
BlobStore + BlobRepository ports (application-layer contracts, FND-06).

No framework types cross these ports. The BlobStore owns the crash-consistent
filesystem protocol (temp write -> hash/size validate -> fsync -> atomic
no-overwrite finalize -> directory fsync) and integrity-verified reads; the
BlobRepository owns the ``blob_objects``/``blob_references`` bookkeeping. The
store commits the database reference ONLY after the filesystem finalize
succeeded (ch19 blob-integrity ordering).

Missing or corrupt referenced content raises :class:`BlobIntegrityError` -
a read never returns empty (or partial) bytes as a substitute.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from milpbooklm_domain.blobs import BlobObject


class BlobIntegrityError(LookupError):
    """
    An integrity incident: referenced blob content is missing or fails its integrity check (ch19).

    Not a not-found convenience: the content of a finalized, referenced blob is
    gone or corrupt. It is never replaced with empty content.
    """


class BlobContentMismatchError(RuntimeError):
    """An existing finalized object does not match its content-addressed identity."""

    # With a correct digest this is unreachable; it means on-disk corruption of
    # the content-addressing itself, and the write refuses to replace it.


class BlobWriteError(RuntimeError):
    """A blob write failed before finalization (validation of the staged temp)."""


@dataclass(frozen=True, slots=True)
class StoredObjectStats:
    """One finalized object on disk: digest, size, and finalization time (mtime)."""

    content_sha256: str
    size_bytes: int
    mtime: datetime


class BlobStore(Protocol):
    """
    Immutable content-addressed blob storage (the crash-consistent finalize protocol).

    Readers only ever see finalized objects: temporaries are unguessable
    (uuid-named) and are never exposed; a finalized object's name is derived
    from its validated digest and it is never mutated or replaced.
    """

    def put(
        self,
        data: bytes | Iterable[bytes],
        *,
        content_type: str | None = None,
        referrer_kind: str | None = None,
        referrer_id: uuid.UUID | None = None,
    ) -> BlobObject:
        """
        Write the bytes and commit the object (plus its reference) durably.

        Runs the full protocol: temp write, streaming hash/size validation,
        fsync, atomic no-overwrite finalize, directory fsync, then the DB
        object/reference commit. Returns the committed BlobObject.
        """
        ...

    def get(self, blob_id: uuid.UUID) -> bytes:
        """
        Read the full content of a finalized blob after verifying its integrity.

        Raises BlobIntegrityError when the record is absent, not finalized,
        or the on-disk bytes are missing/corrupt (never returns a substitute).
        """
        ...

    def verify(self, blob_id: uuid.UUID) -> None:
        """Verify one blob's on-disk bytes against its record; raise on any incident."""
        ...

    def verify_content(self, content_sha256: str, size_bytes: int) -> None:
        """Verify a finalized object by digest (reconciliation's integrity scan)."""
        ...

    def list_temporaries(self) -> tuple[str, ...]:
        """Relative paths of all temporary (staging) files currently on disk."""
        ...

    def list_finals(self) -> tuple[StoredObjectStats, ...]:
        """All finalized objects on disk, keyed by their content digest."""
        ...

    def delete_temporary(self, relative_path: str) -> None:
        """Delete one temporary file (an explicitly invoked sweep action)."""
        ...

    def delete_final(self, content_sha256: str) -> None:
        """Delete one finalized object file (only after the GC safety delay)."""
        ...


class BlobRepository(Protocol):
    """
    Blob bookkeeping over the ``blob_objects``/``blob_references`` tables.

    ``commit_finalized`` is the single DB write of the put protocol: the object
    row and its reference commit in ONE transaction, strictly after the
    filesystem finalize succeeded.
    """

    def commit_finalized(
        self,
        *,
        content_sha256: str,
        size_bytes: int,
        storage_path: str,
        finalized_at: datetime,
        content_type: str | None = None,
        referrer_kind: str | None = None,
        referrer_id: uuid.UUID | None = None,
    ) -> BlobObject:
        """
        Commit the finalized object (and its reference, when given) atomically.

        Content-addressed dedupe: an existing row for the same digest reuses the
        row (completing a stale staging row if one remains); a row whose size
        disagrees with the digest's is an integrity incident.
        """
        ...

    def get(self, blob_id: uuid.UUID) -> BlobObject | None:
        """Return the object record, or None."""
        ...

    def all_objects(self) -> list[BlobObject]:
        """All object records (reconciliation scans every lifecycle state)."""
        ...

    def reference_counts(self) -> dict[uuid.UUID, int]:
        """Return reference counts per blob id (blobs without references are absent)."""
        ...
