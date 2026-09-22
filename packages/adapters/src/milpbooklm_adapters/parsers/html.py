"""Canonical HTML snapshot extraction with readability-style content selection."""

from __future__ import annotations

import re
import sys
import uuid
from dataclasses import dataclass
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
from selectolax.parser import HTMLParser, Node

from .parser_context import WebLocatorContext

_PROFILE: Final = "html-readability-v1"
_REMOVED_SELECTOR: Final = "script,style,noscript,template,nav,header,footer,aside,form"
_CONTAINER_SELECTOR: Final = "main,article,section,div"
_SEMANTIC_TAGS: Final = frozenset(
    {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote", "pre", "td", "th"}
)
_WHITESPACE: Final = re.compile(r"\s+")
_HEADING_TAG_LENGTH: Final = 2


class HtmlCorruptError(Exception):
    """The HTML snapshot cannot produce canonical source content."""


@dataclass(frozen=True, slots=True)
class HtmlBlock:
    """One selected text block with stable DOM and heading ancestry."""

    kind: NodeKind
    text: str
    dom_path: str
    heading_path: tuple[str, ...]
    heading_level: int | None = None


def extract_html_blocks(data: bytes) -> tuple[HtmlBlock, ...]:
    """Extract meaningful blocks after removing executable and chrome elements."""
    tree = HTMLParser(data)
    for node in tree.css(_REMOVED_SELECTOR):
        node.decompose()
    body = tree.body
    if body is None:
        raise HtmlCorruptError("HTML has no document body")
    candidates = [body, *tree.css(_CONTAINER_SELECTOR)]
    content = max(candidates, key=_content_score)
    headings: list[str] = []
    blocks: list[HtmlBlock] = []
    for node in content.traverse():
        if node.tag not in _SEMANTIC_TAGS:
            continue
        if _nested_semantic_node(node, content):
            continue
        text = _normalized_text(node)
        if not text:
            continue
        kind, level = _node_kind(node.tag)
        if level is not None:
            headings[level - 1 :] = [text]
        blocks.append(
            HtmlBlock(
                kind=kind,
                text=text,
                dom_path=_dom_path(node, content),
                heading_path=tuple(headings),
                heading_level=level,
            )
        )
    if not blocks:
        raise HtmlCorruptError("HTML contains no extractable main content")
    return tuple(blocks)


def parse_html(
    source_version_id: uuid.UUID,
    data: bytes,
    web_locator: WebLocatorContext | None = None,
) -> CanonicalDocument:
    """Convert a static HTML snapshot into canonical text-only nodes."""
    blocks = extract_html_blocks(data)
    parser = ParserDescriptor(
        identity="milpbooklm.html",
        version="1",
        profile=_PROFILE,
        tool_versions=(
            f"python={sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        ),
    )
    document_id = canonical_document_id(source_version_id, parser)
    root_id = canonical_node_id(document_id, "document")
    canonical_url = web_locator.canonical_url if web_locator is not None else "upload://html"
    captured_at = web_locator.captured_at if web_locator is not None else "upload"
    nodes = [
        CanonicalNode(
            node_id=root_id,
            kind=NodeKind.DOCUMENT,
            structural_identity="document",
            parent_id=None,
            child_order=0,
            text=None,
            locator=SourceLocator(path=("web", canonical_url, captured_at)),
        )
    ]
    for order, block in enumerate(blocks, start=1):
        identity = f"block:{order}:{block.dom_path}"
        locator_path = (
            "web",
            canonical_url,
            captured_at,
            "dom",
            block.dom_path,
            "heading",
            *block.heading_path,
        )
        nodes.append(
            CanonicalNode(
                node_id=canonical_node_id(document_id, identity),
                kind=block.kind,
                structural_identity=identity,
                parent_id=root_id,
                child_order=order,
                text=block.text,
                locator=SourceLocator(path=locator_path),
                extra_fields=(
                    {"heading_level": block.heading_level}
                    if block.heading_level is not None
                    else {}
                ),
            )
        )
    return CanonicalDocument(
        document_id=document_id,
        source_version_id=source_version_id,
        mime_type="text/html",
        parser=parser,
        languages=(),
        metadata={"canonical_url": canonical_url, "captured_at": captured_at},
        root_node_ids=(root_id,),
        nodes=tuple(nodes),
    )


def _content_score(node: Node) -> int:
    text_length = len(node.text(separator=" ", strip=True))
    paragraphs = len(node.css("p"))
    headings = len(node.css("h1,h2,h3,h4,h5,h6"))
    links = sum(len(link.text(strip=True)) for link in node.css("a"))
    container_bonus = {"main": 10_000, "article": 5_000}.get(node.tag, 0)
    return container_bonus + text_length + (paragraphs * 80) + (headings * 40) - links


def _nested_semantic_node(node: Node, content: Node) -> bool:
    parent = node.parent
    while parent is not None and parent.mem_id != content.mem_id:
        if parent.tag in _SEMANTIC_TAGS:
            return True
        parent = parent.parent
    return False


def _normalized_text(node: Node) -> str:
    separator = "\n" if node.tag == "pre" else " "
    text = node.text(separator=separator, strip=True)
    return text.strip() if node.tag == "pre" else _WHITESPACE.sub(" ", text).strip()


def _node_kind(tag: str) -> tuple[NodeKind, int | None]:
    if tag.startswith("h") and len(tag) == _HEADING_TAG_LENGTH and tag[1].isdigit():
        return NodeKind.HEADING, int(tag[1])
    kinds = {
        "li": NodeKind.LIST_ITEM,
        "blockquote": NodeKind.QUOTE,
        "pre": NodeKind.CODE,
        "td": NodeKind.CELL,
        "th": NodeKind.CELL,
    }
    return kinds.get(tag, NodeKind.PARAGRAPH), None


def _dom_path(node: Node, content: Node) -> str:
    parts: list[str] = []
    current: Node | None = node
    while current is not None:
        position = 1
        sibling = current.prev
        while sibling is not None:
            if sibling.tag == current.tag:
                position += 1
            sibling = sibling.prev
        parts.append(f"{current.tag}:nth-of-type({position})")
        if current.mem_id == content.mem_id:
            break
        current = current.parent
    return ">".join(reversed(parts))
