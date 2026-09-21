"""
Deterministic structural Markdown canonical parser (stdlib only).

Locator guarantees: every node carries a character span over the NFC/LF-
normalized text (the same guarantee as the plain-text parser) plus a stable
``block``-numbered structural path. Embedded markup is never executed; raw
HTML passes through as inert paragraph text.
"""

from __future__ import annotations

import re
import sys
import uuid
from dataclasses import dataclass
from typing import Final

from milpbooklm_contracts.canonical_document import (
    CanonicalDocument,
    CanonicalNode,
    JsonValue,
    NodeKind,
    ParserDescriptor,
    SourceLocator,
    canonical_document_id,
    canonical_node_id,
)

from .textcodec import decode_text

_PROFILE: Final = "markdown-structure-v1"
_ATX_HEADING: Final = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE: Final = re.compile(r"^(```|~~~)\s*(\S*)")
_LIST_ITEM: Final = re.compile(r"^\s*([-*+]|\d+[.)])\s+(.*)$")
_QUOTE: Final = re.compile(r"^>\s?(.*)$")
_TABLE_ROW: Final = re.compile(r"^\s*\|(.+)\|\s*$")
_TABLE_SEPARATOR: Final = re.compile(r"^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$")


@dataclass(frozen=True, slots=True)
class _Line:
    text: str
    start: int


class _NodeBuilder:
    """Accumulate canonical nodes with stable block numbering."""

    def __init__(self, document_id: uuid.UUID, root_id: uuid.UUID, text_length: int) -> None:
        self._document_id = document_id
        self._root_id = root_id
        self._block = 0
        self.nodes: list[CanonicalNode] = [
            CanonicalNode(
                node_id=root_id,
                kind=NodeKind.DOCUMENT,
                structural_identity="document",
                parent_id=None,
                child_order=0,
                text=None,
                locator=SourceLocator(path=("document",), char_start=0, char_end=text_length),
            )
        ]

    def start(
        self,
        kind: NodeKind,
        first: _Line,
        *,
        last: _Line | None = None,
        parent: uuid.UUID | None = None,
        identity_suffix: str = "",
        order: int = 0,
        extra: dict[str, JsonValue] | None = None,
    ) -> uuid.UUID:
        """Create a structural container node and return its id."""
        self._block += 1
        identity = self._identity(kind, identity_suffix)
        node_id = canonical_node_id(self._document_id, identity)
        self.nodes.append(
            CanonicalNode(
                node_id=node_id,
                kind=kind,
                structural_identity=identity,
                parent_id=parent if parent is not None else self._root_id,
                child_order=order if order else self._block,
                text=None,
                locator=self._locator(first, last),
                extra_fields=dict(extra) if extra else {},
            )
        )
        return node_id

    def emit(
        self,
        kind: NodeKind,
        text: str,
        line: _Line,
        *,
        last: _Line | None = None,
        parent: uuid.UUID | None = None,
        identity_suffix: str = "",
        order: int = 0,
        extra: dict[str, JsonValue] | None = None,
    ) -> None:
        """Create one text-bearing node."""
        self._block += 1
        identity = self._identity(kind, identity_suffix)
        self.nodes.append(
            CanonicalNode(
                node_id=canonical_node_id(self._document_id, identity),
                kind=kind,
                structural_identity=identity,
                parent_id=parent if parent is not None else self._root_id,
                child_order=order if order else self._block,
                text=text,
                locator=self._locator(line, last),
                extra_fields=dict(extra) if extra else {},
            )
        )

    def _identity(self, kind: NodeKind, identity_suffix: str) -> str:
        identity = f"{kind.value}:{self._block}"
        return f"{identity}:{identity_suffix}" if identity_suffix else identity

    def _locator(self, first: _Line, last: _Line | None) -> SourceLocator:
        end_line = last if last is not None else first
        return SourceLocator(
            path=("document", "block", str(self._block)),
            char_start=first.start,
            char_end=end_line.start + len(end_line.text),
        )


def parse_markdown(source_version_id: uuid.UUID, data: bytes) -> CanonicalDocument:
    """Convert Markdown bytes into block-addressable canonical nodes."""
    text = decode_text(data)
    parser = ParserDescriptor(
        identity="milpbooklm.markdown",
        version="1",
        profile=_PROFILE,
        tool_versions=(
            f"python={sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        ),
    )
    document_id = canonical_document_id(source_version_id, parser)
    builder = _NodeBuilder(document_id, canonical_node_id(document_id, "document"), len(text))
    lines = _split_lines(text)
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.text.strip():
            index += 1
            continue
        fence = _FENCE.match(line.text)
        if fence:
            index = _emit_code(builder, lines, index, fence.group(1), fence.group(2))
            continue
        heading = _ATX_HEADING.match(line.text)
        if heading:
            builder.emit(
                NodeKind.HEADING,
                heading.group(2).strip(),
                line,
                extra={"heading_level": len(heading.group(1))},
            )
            index += 1
            continue
        if _is_table_start(lines, index):
            index = _emit_table(builder, lines, index)
            continue
        if _LIST_ITEM.match(line.text):
            index = _emit_list(builder, lines, index)
            continue
        if _QUOTE.match(line.text):
            index = _emit_quote(builder, lines, index)
            continue
        index = _emit_paragraph(builder, lines, index)
    return CanonicalDocument(
        document_id=document_id,
        source_version_id=source_version_id,
        mime_type="text/markdown",
        parser=parser,
        languages=(),
        metadata={"normalization": "NFC+LF"},
        root_node_ids=(builder.nodes[0].node_id,),
        nodes=tuple(builder.nodes),
    )


def _split_lines(text: str) -> list[_Line]:
    lines: list[_Line] = []
    start = 0
    for raw in text.split("\n"):
        lines.append(_Line(raw, start))
        start += len(raw) + 1
    return lines


def _is_table_start(lines: list[_Line], index: int) -> bool:
    return (
        index + 1 < len(lines)
        and _TABLE_ROW.match(lines[index].text) is not None
        and _TABLE_SEPARATOR.match(lines[index + 1].text) is not None
        and "-" in lines[index + 1].text
    )


def _row_cells(line: _Line) -> list[str]:
    match = _TABLE_ROW.match(line.text)
    if match is None:
        return []
    return [cell.strip() for cell in match.group(1).split("|")]


def _item_text(line: _Line) -> str:
    match = _LIST_ITEM.match(line.text)
    return match.group(2).strip() if match else line.text.strip()


def _quote_text(line: _Line) -> str:
    match = _QUOTE.match(line.text)
    return match.group(1).strip() if match else line.text.strip()


def _is_plain_continuation(line: _Line) -> bool:
    text = line.text
    return not (
        _ATX_HEADING.match(text)
        or _FENCE.match(text)
        or _LIST_ITEM.match(text)
        or _QUOTE.match(text)
        or _TABLE_ROW.match(text)
    )


def _emit_paragraph(builder: _NodeBuilder, lines: list[_Line], index: int) -> int:
    end = index
    while end < len(lines) and lines[end].text.strip() and _is_plain_continuation(lines[end]):
        end += 1
    body = [line.text.strip() for line in lines[index:end]]
    builder.emit(NodeKind.PARAGRAPH, " ".join(body), lines[index], last=lines[end - 1])
    return end


def _emit_code(
    builder: _NodeBuilder, lines: list[_Line], index: int, marker: str, language: str
) -> int:
    end = index + 1
    while end < len(lines) and not lines[end].text.startswith(marker):
        end += 1
    body = [line.text for line in lines[index + 1 : end]]
    closer = lines[end] if end < len(lines) else lines[-1]
    extra: dict[str, JsonValue] = {}
    if language:
        extra["language"] = language
    builder.emit(NodeKind.CODE, "\n".join(body), lines[index], last=closer, extra=extra)
    return min(end + 1, len(lines))


def _emit_list(builder: _NodeBuilder, lines: list[_Line], index: int) -> int:
    end = index
    while end < len(lines) and _LIST_ITEM.match(lines[end].text):
        end += 1
    items = lines[index:end]
    list_node = builder.start(NodeKind.LIST, items[0], last=items[-1])
    for order, line in enumerate(items, start=1):
        builder.emit(
            NodeKind.LIST_ITEM,
            _item_text(line),
            line,
            parent=list_node,
            identity_suffix=f"item:{order}",
            order=order,
        )
    return end


def _emit_quote(builder: _NodeBuilder, lines: list[_Line], index: int) -> int:
    end = index
    while end < len(lines) and _QUOTE.match(lines[end].text):
        end += 1
    body = [_quote_text(line) for line in lines[index:end]]
    builder.emit(NodeKind.QUOTE, "\n".join(body), lines[index], last=lines[end - 1])
    return end


def _emit_table(builder: _NodeBuilder, lines: list[_Line], index: int) -> int:
    end = index + 2
    while end < len(lines) and _TABLE_ROW.match(lines[end].text):
        end += 1
    table_lines = lines[index:end]
    table_node = builder.start(
        NodeKind.TABLE,
        table_lines[0],
        last=table_lines[-1],
        extra={"header": list[JsonValue](_row_cells(table_lines[0]))},
    )
    for row_number, line in enumerate(table_lines[2:], start=1):
        row_node = builder.start(
            NodeKind.ROW,
            line,
            last=line,
            parent=table_node,
            identity_suffix=f"row:{row_number}",
            order=row_number,
        )
        for column, value in enumerate(_row_cells(line), start=1):
            builder.emit(
                NodeKind.CELL,
                value,
                line,
                parent=row_node,
                identity_suffix=f"row:{row_number}:cell:{column}",
                order=column,
            )
    return end
