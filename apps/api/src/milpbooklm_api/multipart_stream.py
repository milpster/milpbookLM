"""Write-free streaming extraction of one multipart file part."""

from __future__ import annotations

from collections.abc import AsyncIterable, AsyncIterator
from dataclasses import dataclass
from typing import Final

_HEADER_LIMIT: Final = 16 * 1024
_MAX_BOUNDARY_LENGTH: Final = 70


@dataclass(frozen=True, slots=True)
class MultipartError(Exception):
    """A malformed or unsupported multipart request."""

    detail: str

    def __str__(self) -> str:
        """Return the safe parse failure detail."""
        return self.detail


def boundary_from_content_type(content_type: str) -> bytes:
    """Parse and bound the multipart boundary without trusting part metadata."""
    segments = [segment.strip() for segment in content_type.split(";")]
    if not segments or segments[0].lower() != "multipart/form-data":
        raise MultipartError("Content-Type must be multipart/form-data")
    boundary_value = next(
        (segment[9:] for segment in segments[1:] if segment.lower().startswith("boundary=")),
        "",
    ).strip('"')
    try:
        boundary = boundary_value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise MultipartError("multipart boundary must be ASCII") from exc
    if not boundary or len(boundary) > _MAX_BOUNDARY_LENGTH:
        raise MultipartError("multipart boundary is missing or invalid")
    return boundary


async def multipart_file_chunks(
    stream: AsyncIterable[bytes], content_type: str
) -> AsyncIterator[bytes]:
    """Yield the sole `file` part while retaining only a boundary-sized tail."""
    boundary = boundary_from_content_type(content_type)
    opening = b"--" + boundary + b"\r\n"
    marker = b"\r\n--" + boundary
    buffer = bytearray()
    headers_done = False
    async for incoming in stream:
        buffer.extend(incoming)
        if not headers_done:
            if not _strip_headers(buffer, opening):
                continue
            headers_done = True
        while headers_done:
            boundary_index = _final_boundary_index(buffer, marker)
            if boundary_index is not None and boundary_index >= 0:
                if boundary_index:
                    yield bytes(buffer[:boundary_index])
                return
            keep = len(marker) + 2
            if len(buffer) <= keep:
                break
            emit = len(buffer) - keep
            yield bytes(buffer[:emit])
            del buffer[:emit]
    if not headers_done:
        raise MultipartError("multipart headers are incomplete")
    raise MultipartError("multipart closing boundary is missing")


def _strip_headers(buffer: bytearray, opening: bytes) -> bool:
    separator = buffer.find(b"\r\n\r\n")
    if separator < 0:
        if len(buffer) > _HEADER_LIMIT:
            raise MultipartError("multipart headers exceed the limit")
        return False
    header_block = bytes(buffer[:separator])
    if not header_block.startswith(opening):
        raise MultipartError("multipart body has an invalid opening boundary")
    disposition = header_block[len(opening) :].lower()
    if b"content-disposition:" not in disposition or b'name="file"' not in disposition:
        raise MultipartError("multipart request must contain one file field")
    del buffer[: separator + 4]
    return True


def _final_boundary_index(buffer: bytearray, marker: bytes) -> int | None:
    boundary_index = buffer.find(marker)
    if boundary_index < 0:
        return None
    suffix_index = boundary_index + len(marker)
    if len(buffer) < suffix_index + 2:
        return -1
    if bytes(buffer[suffix_index : suffix_index + 2]) != b"--":
        raise MultipartError("multipart request must contain exactly one part")
    return boundary_index
