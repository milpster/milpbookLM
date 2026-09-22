"""Bounded EPUB extraction through EbookLib with inert markup handling."""

from __future__ import annotations

import re
import sys
import tempfile
import uuid
from importlib.metadata import version
from typing import Final

import ebooklib
from ebooklib import epub
from milpbooklm_contracts.canonical_document import (
    CanonicalDocument,
    CanonicalNode,
    NodeKind,
    ParserDescriptor,
    SourceLocator,
    canonical_document_id,
    canonical_node_id,
)

from .html import HtmlCorruptError, extract_html_blocks
from .office import (
    OfficeCorruptError,
    OfficePolicyError,
    OfficeTooLargeError,
    open_bounded_archive,
)

_PROFILE: Final = "epub-ebooklib-v1"
_MAX_MARKUP_BYTES: Final = 4 * 1024 * 1024
_MARKUP_SUFFIXES: Final = (".xml", ".xhtml", ".html", ".htm", ".opf", ".ncx", ".css")
_UNSAFE_DECLARATION: Final = re.compile(
    rb"<!\s*ENTITY\b|<!\s*DOCTYPE\b[^>]*(?:SYSTEM|PUBLIC|\[)", re.IGNORECASE
)
_EXTERNAL_RESOURCE: Final = re.compile(
    rb"(?:src|poster|data)\s*=\s*['\"]\s*(?:https?:)?//|url\(\s*['\"]?(?:https?:)?//",
    re.IGNORECASE,
)


def parse_epub(source_version_id: uuid.UUID, data: bytes) -> CanonicalDocument:
    """Convert an EPUB archive into chapter-addressable canonical nodes."""
    _preflight_epub(data)
    try:
        with tempfile.NamedTemporaryFile(suffix=".epub") as handle:
            handle.write(data)
            handle.flush()
            book = epub.read_epub(handle.name, {"ignore_ncx": True})
    except (epub.EpubException, KeyError, OSError, TypeError) as exc:
        raise OfficeCorruptError("EPUB package is malformed") from exc
    parser = ParserDescriptor(
        identity="milpbooklm.epub",
        version="1",
        profile=_PROFILE,
        tool_versions=(
            f"ebooklib={version('ebooklib')}",
            f"python={sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        ),
    )
    document_id = canonical_document_id(source_version_id, parser)
    root_id = canonical_node_id(document_id, "document")
    nodes = [_root_node(root_id)]
    chapters = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
    for chapter_order, chapter in enumerate(chapters, start=1):
        _append_chapter(
            nodes,
            document_id,
            root_id,
            (chapter_order, chapter.get_name(), chapter.get_content()),
        )
    if len(nodes) == 1:
        raise OfficeCorruptError("EPUB contains no extractable chapters")
    return CanonicalDocument(
        document_id=document_id,
        source_version_id=source_version_id,
        mime_type="application/epub+zip",
        parser=parser,
        languages=(),
        metadata={"chapter_count": len(chapters)},
        root_node_ids=(root_id,),
        nodes=tuple(nodes),
    )


def _preflight_epub(data: bytes) -> None:
    with open_bounded_archive(data) as archive:
        for info in archive.infolist():
            if not info.filename.lower().endswith(_MARKUP_SUFFIXES):
                continue
            if info.file_size > _MAX_MARKUP_BYTES:
                raise OfficeTooLargeError("EPUB markup member exceeds read limit")
            payload = archive.read(info)
            if _UNSAFE_DECLARATION.search(payload):
                raise OfficePolicyError("EPUB contains an unsafe XML declaration")
            if _EXTERNAL_RESOURCE.search(payload):
                raise OfficePolicyError("EPUB contains an external fetch reference")


def _root_node(root_id: uuid.UUID) -> CanonicalNode:
    return CanonicalNode(
        node_id=root_id,
        kind=NodeKind.DOCUMENT,
        structural_identity="document",
        parent_id=None,
        child_order=0,
        text=None,
        locator=SourceLocator(path=("document",)),
    )


def _append_chapter(
    nodes: list[CanonicalNode],
    document_id: uuid.UUID,
    root_id: uuid.UUID,
    chapter: tuple[int, str, bytes],
) -> None:
    chapter_order, chapter_name, content = chapter
    try:
        blocks = extract_html_blocks(content)
    except HtmlCorruptError:
        return
    chapter_identity = f"chapter:{chapter_order}:{chapter_name}"
    chapter_id = canonical_node_id(document_id, chapter_identity)
    nodes.append(
        CanonicalNode(
            node_id=chapter_id,
            kind=NodeKind.SECTION,
            structural_identity=chapter_identity,
            parent_id=root_id,
            child_order=chapter_order,
            text=None,
            locator=SourceLocator(path=("document", "chapter", chapter_name)),
        )
    )
    for block_order, block in enumerate(blocks, start=1):
        identity = f"{chapter_identity}:block:{block_order}:{block.dom_path}"
        nodes.append(
            CanonicalNode(
                node_id=canonical_node_id(document_id, identity),
                kind=block.kind,
                structural_identity=identity,
                parent_id=chapter_id,
                child_order=block_order,
                text=block.text,
                locator=SourceLocator(
                    path=(
                        "document",
                        "chapter",
                        chapter_name,
                        "dom",
                        block.dom_path,
                        "heading",
                        *block.heading_path,
                    )
                ),
            )
        )
