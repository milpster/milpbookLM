"""
Structural chunking over canonical documents (IDX-01, ch08).

Chunking follows the canonical node tree: tables stay intact (never split,
even past the token budget), headings attach to the following unit when the
combined text fits the budget (standalone otherwise), and overflowing
non-table units split at token boundaries. Chunk identities are the
contracts' stable UUIDv5 derivation (node + chunker revision + span), so
re-chunking the same document reproduces identical IDs. The chunker consumes
exactly one CanonicalDocument, so chunks never cross source-version bounds.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Final

from milpbooklm_contracts.canonical_document import (
    CanonicalDocument,
    CanonicalNode,
    NodeKind,
    canonical_chunk_id,
)
from milpbooklm_domain.indexing import (
    STRUCTURAL_CHUNKER_V1,
    Chunk,
    ChunkerProfile,
    NodeSpan,
    estimate_tokens,
)

_WORD_TOKEN: Final = re.compile(r"\S+")


@dataclass(frozen=True, slots=True)
class _Unit:
    """One chunkable text unit extracted from the canonical tree."""

    node_id: uuid.UUID
    char_start: int
    char_end: int
    text: str
    language: str
    kind: NodeKind
    section_ancestry: tuple[uuid.UUID, ...]
    node_spans: tuple[NodeSpan, ...]


def chunk_document(
    document: CanonicalDocument, profile: ChunkerProfile = STRUCTURAL_CHUNKER_V1
) -> tuple[Chunk, ...]:
    """Chunk one canonical document along its structure (deterministic, versioned)."""
    if profile.max_tokens < 1:
        raise ValueError("chunker profile max_tokens must be >= 1")
    units = _collect_units(document)
    drafts = _group_units(units, profile)
    chunks: list[Chunk] = []
    for order, draft in enumerate(drafts):
        chunk_id = canonical_chunk_id(
            draft.node_id, profile.revision, draft.char_start, draft.char_end
        )
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                node_id=draft.node_id,
                char_start=draft.char_start,
                char_end=draft.char_end,
                text=draft.text,
                token_count=estimate_tokens(draft.text),
                language=draft.language,
                section_ancestry=draft.section_ancestry,
                node_spans=draft.node_spans,
                order=order,
            )
        )
    for position, chunk in enumerate(chunks):
        previous = chunks[position - 1].chunk_id if position > 0 else None
        next_chunk = chunks[position + 1].chunk_id if position + 1 < len(chunks) else None
        object.__setattr__(chunk, "prev_chunk_id", previous)
        object.__setattr__(chunk, "next_chunk_id", next_chunk)
    return tuple(chunks)


def _collect_units(document: CanonicalDocument) -> tuple[_Unit, ...]:
    """Walk the canonical tree in document order and extract text units."""
    nodes = {node.node_id: node for node in document.nodes}
    children: dict[uuid.UUID | None, list[CanonicalNode]] = {}
    for node in document.nodes:
        children.setdefault(node.parent_id, []).append(node)
    for siblings in children.values():
        siblings.sort(key=lambda item: item.child_order)
    default_language = document.languages[0] if document.languages else "und"
    units: list[_Unit] = []
    context = _WalkContext(nodes, children, default_language, units)
    for root_id in document.root_node_ids:
        _walk_units(root_id, (), context)
    return tuple(units)


@dataclass(frozen=True, slots=True)
class _WalkContext:
    """The unit-DFS state, bundled to keep the walker's signature short."""

    nodes: dict[uuid.UUID, CanonicalNode]
    children: dict[uuid.UUID | None, list[CanonicalNode]]
    default_language: str
    units: list[_Unit]


def _walk_units(
    node_id: uuid.UUID,
    ancestry: tuple[uuid.UUID, ...],
    context: _WalkContext,
) -> None:
    node = context.nodes[node_id]
    kind = node.kind
    if kind in (
        NodeKind.DOCUMENT,
        NodeKind.SECTION,
        NodeKind.PAGE,
        NodeKind.SLIDE,
        NodeKind.SHEET,
        NodeKind.FIGURE,
        NodeKind.GENERIC,
    ):
        extended = ancestry + (
            (node.node_id,)
            if kind in (NodeKind.SECTION, NodeKind.PAGE, NodeKind.SLIDE, NodeKind.SHEET)
            else ()
        )
        for child in context.children.get(node_id, ()):
            _walk_units(child.node_id, extended, context)
        return
    if kind is NodeKind.HEADING:
        text = node.text or ""
        if text.strip():
            context.units.append(
                _Unit(node.node_id, 0, len(text), text,
                      node.language or context.default_language, kind,
                      (*ancestry, node.node_id),
                      (NodeSpan(node.node_id, 0, len(text)),))
            )
        return
    if kind is NodeKind.LIST:
        for child in context.children.get(node_id, ()):
            _walk_units(child.node_id, ancestry, context)
        return
    text = node.text or ""
    if not text.strip():
        return
    if kind is NodeKind.TABLE:
        table_text = _table_text(node, context.children)
        if table_text.strip():
            context.units.append(
                _Unit(node.node_id, 0, len(table_text), table_text,
                      node.language or context.default_language, kind, ancestry,
                      (NodeSpan(node.node_id, 0, len(table_text)),))
            )
        return
    context.units.append(
        _Unit(node.node_id, 0, len(text), text,
              node.language or context.default_language,
              kind, ancestry, (NodeSpan(node.node_id, 0, len(text)),))
    )


def _table_text(node: CanonicalNode, children: dict[uuid.UUID | None, list[CanonicalNode]]) -> str:
    """Flatten one table (rows/cells preserved) into a single text unit."""
    rows = [child for child in children.get(node.node_id, ()) if child.kind is NodeKind.ROW]
    if rows:
        rendered: list[str] = []
        for row in rows:
            cells = [
                child.text or ""
                for child in children.get(row.node_id, ())
                if child.kind is NodeKind.CELL
            ]
            rendered.append(" | ".join(cells))
        return "\n".join(rendered)
    parts = [child.text or "" for child in children.get(node.node_id, ()) if child.text]
    return "\n".join(part for part in parts if part)


def _group_units(units: tuple[_Unit, ...], profile: ChunkerProfile) -> tuple[_Unit, ...]:
    """Group units into chunks under the token budget (tables stay intact)."""
    grouped: list[_Unit] = []
    index = 0
    while index < len(units):
        unit = units[index]
        if unit.kind is NodeKind.TABLE:
            grouped.append(unit)  # a table is never split, even past the budget
            index += 1
            continue
        if estimate_tokens(unit.text) > profile.max_tokens:
            grouped.extend(_split_unit(unit, profile))
            index += 1
            continue
        if (
            unit.kind is NodeKind.HEADING
            and index + 1 < len(units)
            and units[index + 1].kind is not NodeKind.TABLE
            and estimate_tokens(unit.text + "\n" + units[index + 1].text) <= profile.max_tokens
        ):
            next_unit = units[index + 1]
            grouped.append(_merge_units(unit, next_unit, unit.text + "\n" + next_unit.text))
            index += 2
            continue
        if unit.kind is NodeKind.HEADING:
            grouped.append(unit)  # heading with nothing to attach: own chunk
            index += 1
            continue
        cursor = unit
        position = index + 1
        while position < len(units):
            candidate = units[position]
            if candidate.kind is NodeKind.HEADING:
                break
            if (
                estimate_tokens(candidate.text) > profile.max_tokens
                and candidate.kind is not NodeKind.TABLE
            ):
                break  # an overflowing leaf is emitted standalone
            if estimate_tokens(cursor.text + "\n" + candidate.text) > profile.max_tokens:
                break
            cursor = _merge_units(cursor, candidate, cursor.text + "\n" + candidate.text)
            position += 1
        grouped.append(cursor)
        index = position
    return tuple(grouped)


def _merge_units(first: _Unit, second: _Unit, text: str) -> _Unit:
    """Combine two adjacent units; the FIRST unit's node stays the citation target."""
    return _Unit(
        node_id=first.node_id,
        char_start=first.char_start,
        char_end=first.char_end,
        text=text,
        language=first.language,
        kind=first.kind,
        section_ancestry=first.section_ancestry,
        node_spans=first.node_spans + second.node_spans,
    )


def _split_unit(unit: _Unit, profile: ChunkerProfile) -> tuple[_Unit, ...]:
    """Split one overflowing non-table unit at token boundaries (spans stay mapped)."""
    windows: list[tuple[int, int]] = []
    start = 0
    while start < len(unit.text):
        end = _window_end(unit.text, start, profile.max_tokens)
        windows.append((start, end))
        start = end
    return tuple(
        _Unit(
            node_id=unit.node_id,
            char_start=char_start,
            char_end=char_end,
            text=unit.text[char_start:char_end],
            language=unit.language,
            kind=unit.kind,
            section_ancestry=unit.section_ancestry,
            node_spans=(NodeSpan(unit.node_id, char_start, char_end),),
        )
        for char_start, char_end in windows
    )


def _window_end(text: str, start: int, max_tokens: int) -> int:
    """End of the token window from start (never shorter than one token)."""
    end = start
    for index, match in enumerate(_WORD_TOKEN.finditer(text, start)):
        if index >= max_tokens:
            break
        end = match.end()
    return max(end, min(len(text), start + 1))
