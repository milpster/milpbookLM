"""Deterministic UTF-8 text and Markdown canonical parser."""

from __future__ import annotations

import re
import sys
import unicodedata
import uuid
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

_PARAGRAPH: Final = re.compile(r"\S(?:.*?\S)?(?=\n\s*\n|\s*\Z)", re.DOTALL)
_PROFILE: Final = "text-paragraphs-v1"


def parse_text(source_version_id: uuid.UUID, data: bytes) -> CanonicalDocument:
    """Convert strict UTF-8 bytes into paragraph-addressable canonical nodes."""
    text = unicodedata.normalize("NFC", data.decode("utf-8").replace("\r\n", "\n"))
    parser = ParserDescriptor(
        identity="milpbooklm.text",
        version="1",
        profile=_PROFILE,
        tool_versions=(f"python={sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",),
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
            locator=SourceLocator(path=("document",), char_start=0, char_end=len(text)),
        )
    ]
    for paragraph_number, match in enumerate(_PARAGRAPH.finditer(text), start=1):
        identity = f"paragraph:{paragraph_number}"
        nodes.append(
            CanonicalNode(
                node_id=canonical_node_id(document_id, identity),
                kind=NodeKind.PARAGRAPH,
                structural_identity=identity,
                parent_id=root_id,
                child_order=paragraph_number,
                text=match.group(),
                locator=SourceLocator(
                    path=("document", "paragraph", str(paragraph_number)),
                    char_start=match.start(),
                    char_end=match.end(),
                ),
            )
        )
    return CanonicalDocument(
        document_id=document_id,
        source_version_id=source_version_id,
        mime_type="text/plain",
        parser=parser,
        languages=(),
        metadata={"normalization": "NFC+LF"},
        root_node_ids=(root_id,),
        nodes=tuple(nodes),
    )
