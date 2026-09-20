"""Deterministic PDF canonical parser using the authorized pypdf/pdfplumber chain."""

from __future__ import annotations

import io
import uuid
from importlib.metadata import version
from typing import Final

from milpbooklm_contracts.canonical_document import (
    CanonicalDocument,
    CanonicalNode,
    NodeKind,
    ParserDescriptor,
    SourceLocator,
    canonical_document_id,
    canonical_node_id,
)

_PROFILE: Final = "pypdf-pdfplumber-layout-v1"


def parse_pdf(source_version_id: uuid.UUID, data: bytes) -> CanonicalDocument:
    """Extract page text, text spans, and available word geometry from a PDF."""
    import pdfplumber  # noqa: PLC0415 - network guard must be installed first
    from pdfminer.pdfdocument import PDFPasswordIncorrect  # noqa: PLC0415
    from pdfminer.pdfparser import PDFSyntaxError  # noqa: PLC0415
    from pdfminer.psparser import PSEOF  # noqa: PLC0415
    from pypdf import PdfReader  # noqa: PLC0415
    from pypdf.errors import PdfReadError  # noqa: PLC0415

    try:
        reader = PdfReader(io.BytesIO(data), strict=True)
    except PDFPasswordIncorrect as exc:
        raise PdfEncryptedError from exc
    except (PdfReadError, PDFSyntaxError, PSEOF, ValueError) as exc:
        raise PdfCorruptError from exc
    if reader.is_encrypted:
        raise PdfEncryptedError
    parser = ParserDescriptor(
        identity="milpbooklm.pdf",
        version="1",
        profile=_PROFILE,
        tool_versions=(
            f"pypdf={version('pypdf')}",
            f"pdfplumber={version('pdfplumber')}",
            f"pdfminer.six={version('pdfminer.six')}",
        ),
    )
    document_id = canonical_document_id(source_version_id, parser)
    root_id = canonical_node_id(document_id, "document")
    nodes = [
        CanonicalNode(
            node_id=root_id,
            kind=NodeKind.DOCUMENT,
            structural_identity="document",
            parent_id=None,
            child_order=0,
            text=None,
            locator=SourceLocator(path=("document",)),
        )
    ]
    try:
        with pdfplumber.open(io.BytesIO(data)) as document:
            for page_number, page in enumerate(document.pages, start=1):
                page_identity = f"page:{page_number}"
                page_id = canonical_node_id(document_id, page_identity)
                nodes.append(
                    CanonicalNode(
                        node_id=page_id,
                        kind=NodeKind.PAGE,
                        structural_identity=page_identity,
                        parent_id=root_id,
                        child_order=page_number,
                        text=None,
                        locator=SourceLocator(
                            path=("document", "page", str(page_number)),
                            page=page_number,
                            bbox=(0.0, 0.0, float(page.width), float(page.height)),
                        ),
                    )
                )
                words = page.extract_words(keep_blank_chars=False, use_text_flow=True)
                text = " ".join(str(word["text"]) for word in words).strip()
                if not text:
                    continue
                paragraph_identity = f"page:{page_number}:paragraph:1"
                nodes.append(
                    CanonicalNode(
                        node_id=canonical_node_id(document_id, paragraph_identity),
                        kind=NodeKind.PARAGRAPH,
                        structural_identity=paragraph_identity,
                        parent_id=page_id,
                        child_order=1,
                        text=text,
                        locator=SourceLocator(
                            path=("document", "page", str(page_number), "paragraph", "1"),
                            char_start=0,
                            char_end=len(text),
                            page=page_number,
                            bbox=_word_bbox(words),
                        ),
                    )
                )
    except PDFPasswordIncorrect as exc:
        raise PdfEncryptedError from exc
    except (PdfReadError, PDFSyntaxError, PSEOF, ValueError) as exc:
        raise PdfCorruptError from exc
    return CanonicalDocument(
        document_id=document_id,
        source_version_id=source_version_id,
        mime_type="application/pdf",
        parser=parser,
        languages=(),
        metadata={"page_count": len(reader.pages)},
        root_node_ids=(root_id,),
        nodes=tuple(nodes),
    )


class PdfEncryptedError(Exception):
    """The PDF requires a password and cannot be parsed."""


class PdfCorruptError(Exception):
    """The PDF structure cannot be parsed by the authorized chain."""


def _word_bbox(
    words: list[dict[str, int | float | str | bool]],
) -> tuple[float, float, float, float]:
    return (
        min(float(word["x0"]) for word in words),
        min(float(word["top"]) for word in words),
        max(float(word["x1"]) for word in words),
        max(float(word["bottom"]) for word in words),
    )
