"""Bounded streaming quarantine and byte-based text/PDF identification."""

from __future__ import annotations

import codecs
import hashlib
import os
import uuid
from collections.abc import AsyncIterable, Iterable, Iterator
from pathlib import Path
from typing import Final

from milpbooklm_application.source_acquisition import QuarantinedPayload
from milpbooklm_domain.acquisition import (
    AcquisitionError,
    AcquisitionErrorCode,
    IdentifiedMedia,
)

_CHUNK_SIZE: Final = 1024 * 1024
_PDF_MAGIC: Final = b"%PDF-"
_PDF_ENCRYPT_MARKER: Final = b"/Encrypt"


class FilesystemQuarantineStore:
    """Store untrusted bytes only under the configured quarantine directory."""

    def __init__(self, root: Path, *, max_bytes: int) -> None:
        """Bind the quarantine below the blob root and its streaming byte limit."""
        self._root = root / "quarantine"
        self._max_bytes = max_bytes
        self._root.mkdir(parents=True, exist_ok=True)

    async def acquire(self, chunks: AsyncIterable[bytes]) -> QuarantinedPayload:
        """Abort at the first over-limit chunk, leaving no quarantine residue."""
        path = self._root / f"{uuid.uuid4()}.quarantine"
        digest = hashlib.sha256()
        size = 0
        completed = False
        try:
            with path.open("xb") as handle:
                async for chunk in chunks:
                    next_size = size + len(chunk)
                    if next_size > self._max_bytes:
                        raise AcquisitionError(
                            AcquisitionErrorCode.TOO_LARGE,
                            f"source exceeds {self._max_bytes} byte acquisition limit",
                        )
                    handle.write(chunk)
                    digest.update(chunk)
                    size = next_size
                handle.flush()
                os.fsync(handle.fileno())
            media = self._identify(path, size)
            self._fsync_root()
            completed = True
            return QuarantinedPayload(path, digest.hexdigest(), size, media)
        finally:
            if not completed:
                path.unlink(missing_ok=True)
                self._fsync_root()

    def chunks(self, payload: QuarantinedPayload) -> Iterable[bytes]:
        """Yield a validated quarantine file in bounded chunks."""
        return self._read_chunks(payload.path)

    def discard(self, payload: QuarantinedPayload) -> None:
        """Remove the quarantine file after finalization or failure."""
        payload.path.unlink(missing_ok=True)
        self._fsync_root()

    @staticmethod
    def _read_chunks(path: Path) -> Iterator[bytes]:
        with path.open("rb") as handle:
            while chunk := handle.read(_CHUNK_SIZE):
                yield chunk

    @staticmethod
    def _identify(path: Path, size: int) -> IdentifiedMedia:
        if size == 0:
            raise AcquisitionError(AcquisitionErrorCode.CORRUPT, "source is empty")
        with path.open("rb") as handle:
            prefix = handle.read(len(_PDF_MAGIC))
        if prefix == _PDF_MAGIC:
            encrypted = any(
                _PDF_ENCRYPT_MARKER in chunk
                for chunk in FilesystemQuarantineStore._read_chunks(path)
            )
            if encrypted:
                raise AcquisitionError(
                    AcquisitionErrorCode.POLICY_BLOCKED, "encrypted PDF is not accepted"
                )
            return IdentifiedMedia.PDF
        decoder = codecs.getincrementaldecoder("utf-8")("strict")
        try:
            for chunk in FilesystemQuarantineStore._read_chunks(path):
                decoder.decode(chunk)
            decoder.decode(b"", final=True)
        except UnicodeDecodeError as exc:
            raise AcquisitionError(
                AcquisitionErrorCode.UNSUPPORTED,
                "content is neither a PDF nor UTF-8 text",
            ) from exc
        return IdentifiedMedia.TEXT

    def _fsync_root(self) -> None:
        fd = os.open(self._root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
