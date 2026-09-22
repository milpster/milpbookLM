"""Bounded streaming quarantine and byte-based text/PDF identification."""

from __future__ import annotations

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

from milpbooklm_adapters.parsers.sniffing import SNIFF_SAMPLE_BYTES, sniff_media_type
from milpbooklm_adapters.parsers.textcodec import validate_text_stream

_CHUNK_SIZE: Final = 1024 * 1024
_PDF_ENCRYPT_MARKER: Final = b"/Encrypt"
_TEXT_FAMILY: Final = frozenset(
    {IdentifiedMedia.TEXT, IdentifiedMedia.MARKDOWN, IdentifiedMedia.CSV, IdentifiedMedia.HTML}
)


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
            prefix = handle.read(SNIFF_SAMPLE_BYTES)
        media = sniff_media_type(prefix)
        if media is None:
            raise AcquisitionError(
                AcquisitionErrorCode.UNSUPPORTED,
                "content is not an accepted PDF, office, or decodable text family",
            )
        if media is IdentifiedMedia.PDF:
            if any(
                _PDF_ENCRYPT_MARKER in chunk
                for chunk in FilesystemQuarantineStore._read_chunks(path)
            ):
                raise AcquisitionError(
                    AcquisitionErrorCode.POLICY_BLOCKED, "encrypted PDF is not accepted"
                )
        elif media in _TEXT_FAMILY and _text_rejected(path):
            raise AcquisitionError(
                AcquisitionErrorCode.UNSUPPORTED,
                "text content is not decodable after BOM detection",
            )
        return media

    def _fsync_root(self) -> None:
        fd = os.open(self._root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _text_rejected(path: Path) -> bool:
    return validate_text_stream(FilesystemQuarantineStore._read_chunks(path)) is not None
