"""Strict JSON decoder for canonical schema version 1."""

from __future__ import annotations

import uuid

from milpbooklm_contracts.canonical_document import (
    BBOX_COORDINATE_COUNT,
    SCHEMA_VERSION,
    AuthorityClass,
    CanonicalContractError,
    CanonicalDocument,
    CanonicalNode,
    JsonValue,
    NodeKind,
    ParserDescriptor,
    SourceLocator,
)


def canonical_document_from_json(value: dict[str, JsonValue]) -> CanonicalDocument:
    """Decode version-1 JSON while preserving fields unknown to this reader."""
    if value.get("schema_version") != SCHEMA_VERSION:
        raise CanonicalContractError("unsupported canonical schema version")
    parser_value = _mapping(value.get("parser"), "parser")
    parser = ParserDescriptor(
        identity=_text(parser_value.get("identity"), "parser.identity"),
        version=_text(parser_value.get("version"), "parser.version"),
        profile=_text(parser_value.get("profile"), "parser.profile"),
        tool_versions=tuple(
            _text(item, "parser.tool_versions[]")
            for item in _sequence(parser_value.get("tool_versions"), "parser.tool_versions")
        ),
        extra_fields=_unknown(parser_value, {"identity", "version", "profile", "tool_versions"}),
    )
    return CanonicalDocument(
        document_id=uuid.UUID(_text(value.get("document_id"), "document_id")),
        source_version_id=uuid.UUID(_text(value.get("source_version_id"), "source_version_id")),
        mime_type=_text(value.get("mime_type"), "mime_type"),
        parser=parser,
        languages=tuple(
            _text(item, "languages[]")
            for item in _sequence(value.get("languages"), "languages")
        ),
        metadata=_mapping(value.get("metadata"), "metadata"),
        root_node_ids=tuple(
            uuid.UUID(_text(item, "root_node_ids[]"))
            for item in _sequence(value.get("root_node_ids"), "root_node_ids")
        ),
        nodes=tuple(
            _node(_mapping(item, "nodes[]"))
            for item in _sequence(value.get("nodes"), "nodes")
        ),
        extra_fields=_unknown(
            value,
            {
                "schema_version", "document_id", "source_version_id", "mime_type",
                "parser", "languages", "metadata", "root_node_ids", "nodes",
            },
        ),
    )


def _node(value: dict[str, JsonValue]) -> CanonicalNode:
    locator_value = _mapping(value.get("locator"), "node.locator")
    bbox_value = locator_value.get("bbox")
    bbox_items = None if bbox_value is None else _sequence(bbox_value, "node.locator.bbox")
    bbox = None
    if bbox_items is not None:
        if len(bbox_items) != BBOX_COORDINATE_COUNT:
            raise CanonicalContractError("node.locator.bbox must have four coordinates")
        bbox = (
            float(_number(bbox_items[0], "node.locator.bbox[]")),
            float(_number(bbox_items[1], "node.locator.bbox[]")),
            float(_number(bbox_items[2], "node.locator.bbox[]")),
            float(_number(bbox_items[3], "node.locator.bbox[]")),
        )
    locator = SourceLocator(
        path=tuple(
            _text(item, "node.locator.path[]")
            for item in _sequence(locator_value.get("path"), "node.locator.path")
        ),
        char_start=_optional_int(locator_value.get("char_start"), "node.locator.char_start"),
        char_end=_optional_int(locator_value.get("char_end"), "node.locator.char_end"),
        page=_optional_int(locator_value.get("page"), "node.locator.page"),
        bbox=bbox,
        extra_fields=_unknown(locator_value, {"path", "char_start", "char_end", "page", "bbox"}),
    )
    parent = value.get("parent_id")
    return CanonicalNode(
        node_id=uuid.UUID(_text(value.get("node_id"), "node.node_id")),
        kind=NodeKind(_text(value.get("kind"), "node.kind")),
        structural_identity=_text(value.get("structural_identity"), "node.structural_identity"),
        parent_id=None if parent is None else uuid.UUID(_text(parent, "node.parent_id")),
        child_order=_integer(value.get("child_order"), "node.child_order"),
        text=_optional_text(value.get("text"), "node.text"),
        locator=locator,
        authority=AuthorityClass(_text(value.get("authority"), "node.authority")),
        language=_optional_text(value.get("language"), "node.language"),
        extra_fields=_unknown(
            value,
            {
                "node_id", "kind", "structural_identity", "parent_id", "child_order",
                "text", "locator", "authority", "language",
            },
        ),
    )


def _mapping(value: JsonValue, field_name: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise CanonicalContractError(f"{field_name} must be an object")
    return value


def _sequence(value: JsonValue, field_name: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise CanonicalContractError(f"{field_name} must be an array")
    return value


def _text(value: JsonValue, field_name: str) -> str:
    if not isinstance(value, str):
        raise CanonicalContractError(f"{field_name} must be text")
    return value


def _optional_text(value: JsonValue, field_name: str) -> str | None:
    return None if value is None else _text(value, field_name)


def _integer(value: JsonValue, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise CanonicalContractError(f"{field_name} must be an integer")
    return value


def _optional_int(value: JsonValue, field_name: str) -> int | None:
    return None if value is None else _integer(value, field_name)


def _number(value: JsonValue, field_name: str) -> int | float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise CanonicalContractError(f"{field_name} must be numeric")
    return value


def _unknown(value: dict[str, JsonValue], known: set[str]) -> dict[str, JsonValue]:
    return {key: item for key, item in value.items() if key not in known}
