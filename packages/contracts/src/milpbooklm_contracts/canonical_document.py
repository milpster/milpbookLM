"""Versioned, format-neutral canonical document contract."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final, override

SCHEMA_VERSION: Final = "1"
CHUNK_NAMESPACE: Final = uuid.UUID("957b9510-9cc5-5ba7-b04c-068c5e647b50")
BBOX_COORDINATE_COUNT: Final = 4
type JsonValue = str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None


class NodeKind(StrEnum):
    """Closed node-kind set for canonical schema version 1."""

    DOCUMENT = "document"
    SECTION = "section"
    PARAGRAPH = "paragraph"
    HEADING = "heading"
    LIST = "list"
    LIST_ITEM = "list_item"
    QUOTE = "quote"
    CODE = "code"
    TABLE = "table"
    ROW = "row"
    CELL = "cell"
    IMAGE = "image"
    FIGURE = "figure"
    CAPTION = "caption"
    PAGE = "page"
    SLIDE = "slide"
    SHEET = "sheet"
    TRANSCRIPT_SEGMENT = "transcript_segment"
    SPEAKER_TURN = "speaker_turn"
    ATTACHMENT = "attachment"
    REFERENCE = "reference"
    GENERIC = "generic"


class AuthorityClass(StrEnum):
    """Origin classification for canonical content."""

    SOURCE_AUTHORED = "source_authored"
    PARSER_TRANSFORMED = "parser_transformed"
    OCR = "ocr"
    MODEL_DERIVED = "model_derived"
    HUMAN_ANNOTATION = "human_annotation"


@dataclass(frozen=True, slots=True)
class CanonicalContractError(Exception):
    """A canonical JSON value violates schema version 1."""

    detail: str

    @override
    def __str__(self) -> str:
        """Describe the rejected contract without including source content."""
        return self.detail


@dataclass(frozen=True, slots=True)
class ParserDescriptor:
    """Parser identity and reproducibility metadata."""

    identity: str
    version: str
    profile: str
    tool_versions: tuple[str, ...]
    extra_fields: dict[str, JsonValue] = field(default_factory=dict)

    def to_json(self) -> dict[str, JsonValue]:
        """Serialize while retaining unknown parser fields."""
        value = dict(self.extra_fields)
        value.update(
            identity=self.identity,
            version=self.version,
            profile=self.profile,
            tool_versions=list(self.tool_versions),
        )
        return value


@dataclass(frozen=True, slots=True)
class SourceLocator:
    """Structural path and optional text/PDF coordinates."""

    path: tuple[str, ...]
    char_start: int | None = None
    char_end: int | None = None
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    extra_fields: dict[str, JsonValue] = field(default_factory=dict)

    def to_json(self) -> dict[str, JsonValue]:
        """Serialize while retaining unknown locator fields."""
        value = dict(self.extra_fields)
        value["path"] = list(self.path)
        bbox: list[JsonValue] | None = None
        if self.bbox is not None:
            bbox = [self.bbox[0], self.bbox[1], self.bbox[2], self.bbox[3]]
        optional_fields: dict[str, JsonValue] = {
            key: item
            for key, item in {
                "char_start": self.char_start,
                "char_end": self.char_end,
                "page": self.page,
                "bbox": bbox,
            }.items()
            if item is not None
        }
        value.update(optional_fields)
        return value


@dataclass(frozen=True, slots=True)
class CanonicalNode:
    """One immutable structural unit and its source locator."""

    node_id: uuid.UUID
    kind: NodeKind
    structural_identity: str
    parent_id: uuid.UUID | None
    child_order: int
    text: str | None
    locator: SourceLocator
    authority: AuthorityClass = AuthorityClass.SOURCE_AUTHORED
    language: str | None = None
    extra_fields: dict[str, JsonValue] = field(default_factory=dict)

    def to_json(self) -> dict[str, JsonValue]:
        """Serialize while retaining unknown node fields."""
        value = dict(self.extra_fields)
        value.update(
            node_id=str(self.node_id),
            kind=self.kind.value,
            structural_identity=self.structural_identity,
            parent_id=str(self.parent_id) if self.parent_id is not None else None,
            child_order=self.child_order,
            text=self.text,
            locator=self.locator.to_json(),
            authority=self.authority.value,
            language=self.language,
        )
        return value


@dataclass(frozen=True, slots=True)
class CanonicalDocument:
    """Immutable canonical representation of one source version."""

    document_id: uuid.UUID
    source_version_id: uuid.UUID
    mime_type: str
    parser: ParserDescriptor
    languages: tuple[str, ...]
    metadata: dict[str, JsonValue]
    root_node_ids: tuple[uuid.UUID, ...]
    nodes: tuple[CanonicalNode, ...]
    schema_version: str = SCHEMA_VERSION
    extra_fields: dict[str, JsonValue] = field(default_factory=dict)

    def to_json(self) -> dict[str, JsonValue]:
        """Serialize while preserving unknown document, parser, node, and locator fields."""
        value = dict(self.extra_fields)
        value.update(
            schema_version=self.schema_version,
            document_id=str(self.document_id),
            source_version_id=str(self.source_version_id),
            mime_type=self.mime_type,
            parser=self.parser.to_json(),
            languages=list(self.languages),
            metadata=self.metadata,
            root_node_ids=[str(node_id) for node_id in self.root_node_ids],
            nodes=[node.to_json() for node in self.nodes],
        )
        return value

    @classmethod
    def from_json(cls, value: dict[str, JsonValue]) -> CanonicalDocument:
        """Parse version-1 canonical JSON and preserve every unknown field."""
        from milpbooklm_contracts.canonical_codec import (  # noqa: PLC0415
            canonical_document_from_json,
        )

        return canonical_document_from_json(value)


def canonical_document_id(source_version_id: uuid.UUID, parser: ParserDescriptor) -> uuid.UUID:
    """Derive a stable representation ID from immutable version and parser identities."""
    identity = f"canonical:{SCHEMA_VERSION}:{parser.identity}:{parser.version}:{parser.profile}"
    return uuid.uuid5(source_version_id, identity)


def canonical_node_id(document_id: uuid.UUID, structural_identity: str) -> uuid.UUID:
    """Derive a stable node ID from parser-stable structural identity."""
    return uuid.uuid5(document_id, structural_identity)


def canonical_chunk_id(
    node_id: uuid.UUID, chunker_revision: str, start: int, end: int
) -> uuid.UUID:
    """Derive a stable chunk ID from node identity, chunker revision, and text span."""
    return uuid.uuid5(CHUNK_NAMESPACE, f"{node_id}:{chunker_revision}:{start}:{end}")
