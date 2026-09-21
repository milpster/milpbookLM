"""
BOM-bound streaming text decoding for the Markdown/CSV families.

The accepted encodings are exactly UTF-8 (with or without BOM) and UTF-16
with a BOM; detection consumes only the leading byte-order mark (the guide's
"bounded" BOM/encoding detection). Anything else fails strict decoding and
surfaces as an explicit corrupt state — never a silently re-encoded document.
"""

from __future__ import annotations

import codecs
import unicodedata
from collections.abc import Iterator
from typing import Final

_UTF8_BOM: Final = b"\xef\xbb\xbf"
_UTF16_BOMS: Final = (b"\xff\xfe", b"\xfe\xff")


def bom_encoding(data: bytes) -> str | None:
    """Return the BOM-derived encoding for a payload, or None for plain UTF-8."""
    if data.startswith(_UTF8_BOM) or not data.startswith(_UTF16_BOMS):
        return None
    return "utf-16"


def decode_text(data: bytes) -> str:
    """Decode BOM-detected text, normalize to NFC with LF line endings."""
    encoding = bom_encoding(data)
    if encoding is None:
        text = data.decode("utf-8")
        if data.startswith(_UTF8_BOM):
            text = text[1:]
    else:
        text = data.decode(encoding)
    return unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))


def validate_text_stream(chunks: Iterator[bytes]) -> str | None:
    """Strictly validate every chunk; return a rejection code or None."""
    first = next(chunks, b"")
    decoder = codecs.getincrementaldecoder(bom_encoding(first) or "utf-8")("strict")
    try:
        decoder.decode(first)
        for chunk in chunks:
            decoder.decode(chunk)
        decoder.decode(b"", final=True)
    except UnicodeDecodeError:
        return "corrupt"
    return None
