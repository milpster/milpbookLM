"""
Filesystem BlobStore (FND-06; ch19 "blob integrity" protocol).

Layout under the configured blob root:

    tmp/<uuid>.tmp          staged writes (unguessable names; never exposed to readers)
    objects/<aa>/<sha256>   finalized, content-addressed, immutable objects

Crash-consistent ordering of ``put``:
  1. stream the bytes into a fresh temp file, computing SHA-256 + size en route
  2. flush + fsync the temp file
  3. re-validate the temp on disk (digest + size)
  4. atomic NO-OVERWRITE finalize: ``os.link`` (EEXIST means an identical
     content-addressed object already exists; a mismatch is an incident)
  5. fsync the objects directory (and the tmp directory after the unlink)
  6. commit the DB object/reference row (one transaction, strictly AFTER 4-5)

A crash anywhere in this sequence leaves either a sweepable orphan temp, or a
complete, self-verifying finalized object without a reference (an unreferenced
final) - never a partial final file, and never a database reference to data
that is missing.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from milpbooklm_application.blob_store import (
    BlobContentMismatchError,
    BlobIntegrityError,
    BlobRepository,
    BlobWriteError,
    StoredObjectStats,
)
from milpbooklm_application.ports import Clock
from milpbooklm_domain.blobs import BlobObject, BlobState

# 1 MiB streaming chunks: bounds memory for large objects while hashing.
_CHUNK_SIZE = 1024 * 1024
_TMP_DIRNAME = "tmp"
_OBJECTS_DIRNAME = "objects"
_TMP_SUFFIX = ".tmp"


class FilesystemBlobStore:
    """The local-filesystem BlobStore (the default blob adapter, guide 03)."""

    def __init__(self, root: Path, repo: BlobRepository, clock: Clock) -> None:
        """Wire the blob root, the bookkeeping repository, and the clock."""
        self._root = Path(root)
        self._tmp_dir = self._root / _TMP_DIRNAME
        self._objects_dir = self._root / _OBJECTS_DIRNAME
        self._repo = repo
        self._clock = clock
        self._tmp_dir.mkdir(parents=True, exist_ok=True)
        self._objects_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ paths

    def _final_path(self, content_sha256: str) -> Path:
        """Return the content-addressed final path for a validated digest."""
        return self._objects_dir / content_sha256[:2] / content_sha256

    # -------------------------------------------------------------------- put

    def put(
        self,
        data: bytes | Iterable[bytes],
        *,
        content_type: str | None = None,
        referrer_kind: str | None = None,
        referrer_id: uuid.UUID | None = None,
    ) -> BlobObject:
        """Write, validate, finalize, then commit the DB record (the full protocol)."""
        temp, expected_sha, expected_size = self._write_temporary(data)
        try:
            self._validate_temporary(temp, expected_sha, expected_size)
            self._finalize(temp, expected_sha, expected_size)
        finally:
            temp.unlink(missing_ok=True)
        return self._repo.commit_finalized(
            content_sha256=expected_sha,
            size_bytes=expected_size,
            storage_path=self._final_path(expected_sha).relative_to(self._root).as_posix(),
            finalized_at=self._clock.now(),
            content_type=content_type,
            referrer_kind=referrer_kind,
            referrer_id=referrer_id,
        )

    def _write_temporary(
        self, data: bytes | Iterable[bytes]
    ) -> tuple[Path, str, int]:
        """Stream the bytes into a fresh fsync'd temp file; return (path, sha, size)."""
        temp = self._tmp_dir / f"{uuid.uuid4()}{_TMP_SUFFIX}"
        chunks: Iterable[bytes]
        chunks = (bytes(data),) if isinstance(data, (bytes, bytearray, memoryview)) else data
        digest = hashlib.sha256()
        size = 0
        with temp.open("wb") as fh:
            for chunk in chunks:
                fh.write(chunk)
                digest.update(chunk)
                size += len(chunk)
            fh.flush()
            os.fsync(fh.fileno())
        return temp, digest.hexdigest(), size

    @staticmethod
    def _hash_file(path: Path) -> tuple[str, int]:
        """Stream-hash a file; return (sha256 hex, byte count)."""
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as fh:
            while chunk := fh.read(_CHUNK_SIZE):
                digest.update(chunk)
                size += len(chunk)
        return digest.hexdigest(), size

    def _validate_temporary(self, temp: Path, expected_sha: str, expected_size: int) -> None:
        """Re-read the staged temp and confirm its digest + size before finalize."""
        sha, size = self._hash_file(temp)
        if sha != expected_sha or size != expected_size:
            raise BlobWriteError(
                f"staged temporary failed validation (sha={sha[:12]}..., size={size})"
            )

    def _finalize(self, temp: Path, content_sha256: str, size_bytes: int) -> None:
        """Atomically publish the temp as the content-addressed final object."""
        final = self._final_path(content_sha256)
        if final.exists():
            self._require_identical(final, content_sha256, size_bytes)
        else:
            final.parent.mkdir(parents=True, exist_ok=True)
            try:
                # link() is atomic on POSIX and refuses to overwrite (EEXIST):
                # an existing final is NEVER replaced.
                os.link(temp, final)
            except FileExistsError:
                # A concurrent writer won the race; content addressing makes
                # the existing object identical - verify, then dedupe.
                self._require_identical(final, content_sha256, size_bytes)
            self._fsync_dir(final.parent)
        self._fsync_dir(self._tmp_dir)

    @staticmethod
    def _require_identical(final: Path, content_sha256: str, size_bytes: int) -> None:
        """Refuse to replace an existing final object whose bytes do not match."""
        sha, size = FilesystemBlobStore._hash_file(final)
        if sha != content_sha256 or size != size_bytes:
            raise BlobContentMismatchError(
                f"existing final object {content_sha256} does not match its identity"
            )

    @staticmethod
    def _fsync_dir(directory: Path) -> None:
        """Fsync a directory so a rename/link of its entries is durable."""
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    # ------------------------------------------------------------------- reads

    def get(self, blob_id: uuid.UUID) -> bytes:
        """Read a finalized blob's bytes after verifying its integrity."""
        blob = self._require_finalized_record(blob_id)
        path = self._root / blob.storage_path
        if not path.is_file():
            raise BlobIntegrityError(
                f"finalized blob {blob_id} ({blob.content_sha256}) is missing on disk"
            )
        data = path.read_bytes()
        if len(data) != blob.size_bytes:
            raise BlobIntegrityError(
                f"finalized blob {blob_id} ({blob.content_sha256}) size mismatch "
                f"(expected {blob.size_bytes}, found {len(data)})"
            )
        if hashlib.sha256(data).hexdigest() != blob.content_sha256:
            raise BlobIntegrityError(
                f"finalized blob {blob_id} ({blob.content_sha256}) failed its digest check"
            )
        return data

    def verify(self, blob_id: uuid.UUID) -> None:
        """Verify one blob's on-disk bytes against its record (no content returned)."""
        blob = self._require_finalized_record(blob_id)
        path = self._root / blob.storage_path
        if not path.is_file():
            raise BlobIntegrityError(
                f"finalized blob {blob_id} ({blob.content_sha256}) is missing on disk"
            )
        sha, size = self._hash_file(path)
        if sha != blob.content_sha256 or size != blob.size_bytes:
            raise BlobIntegrityError(
                f"finalized blob {blob_id} ({blob.content_sha256}) failed its integrity check"
            )

    def verify_content(self, content_sha256: str, size_bytes: int) -> None:
        """Verify a finalized object by digest (reconciliation's integrity scan)."""
        path = self._final_path(content_sha256)
        if not path.is_file():
            raise BlobIntegrityError(f"finalized object {content_sha256} is missing on disk")
        sha, size = self._hash_file(path)
        if sha != content_sha256 or size != size_bytes:
            raise BlobIntegrityError(
                f"finalized object {content_sha256} failed its integrity check "
                f"(expected {size_bytes} bytes, found {size})"
            )

    def _require_finalized_record(self, blob_id: uuid.UUID) -> BlobObject:
        """Load the record; a missing or non-finalized record is an incident."""
        blob = self._repo.get(blob_id)
        if blob is None:
            raise BlobIntegrityError(f"referenced blob {blob_id} has no object record")
        if blob.state is not BlobState.FINALIZED:
            raise BlobIntegrityError(
                f"blob {blob_id} is in state {blob.state.value}, not finalized"
            )
        return blob

    # -------------------------------------------------------------- inventory

    def list_temporaries(self) -> tuple[str, ...]:
        """Relative paths of all staged temp files (reconciliation input)."""
        if not self._tmp_dir.is_dir():
            return ()
        return tuple(
            sorted(
                path.relative_to(self._root).as_posix()
                for path in self._tmp_dir.iterdir()
                if path.is_file() and path.name.endswith(_TMP_SUFFIX)
            )
        )

    def list_finals(self) -> tuple[StoredObjectStats, ...]:
        """All finalized objects on disk, with size + mtime (reconciliation input)."""
        stats: list[StoredObjectStats] = []
        if not self._objects_dir.is_dir():
            return ()
        for bucket in sorted(self._objects_dir.iterdir()):
            if not bucket.is_dir():
                continue
            for path in sorted(bucket.iterdir()):
                if not path.is_file():
                    continue
                info = path.stat()
                stats.append(
                    StoredObjectStats(
                        content_sha256=path.name,
                        size_bytes=info.st_size,
                        mtime=datetime.fromtimestamp(info.st_mtime, tz=UTC),
                    )
                )
        return tuple(stats)

    # ------------------------------------------------------------------ sweep

    def delete_temporary(self, relative_path: str) -> None:
        """Delete one staged temp file (sweep action; temps are never referenced)."""
        path = self._root / relative_path
        if path.parent != self._tmp_dir:
            raise ValueError(f"not a temporary path: {relative_path}")
        path.unlink(missing_ok=True)

    def delete_final(self, content_sha256: str) -> None:
        """Delete one finalized object file (only after the GC safety delay)."""
        path = self._final_path(content_sha256)
        path.unlink(missing_ok=True)
        # The bucket dir is absent when the object was already gone (a
        # record-only unreferenced finding); fsync only what exists.
        if path.parent.is_dir():
            self._fsync_dir(path.parent)
