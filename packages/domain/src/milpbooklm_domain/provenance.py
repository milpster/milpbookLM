"""
Provenance graph vocabulary (ch07 "Canonical Document and Provenance Contracts").

The provenance graph stores typed edges between content-bearing objects. An edge reads
"from_node <edge_type> to_node": an artifact names the object it originates from, so
ancestor traversal follows each edge's `to` endpoint. Traversal is bounded and
cycle-safe; purge dependencies are inferred from these rows plus manifest/blob/cache
ownership - never from vector similarity.
"""

from __future__ import annotations

from enum import StrEnum


class ProvenanceEdgeType(StrEnum):
    """The six closed provenance edge relations (ch07)."""

    DERIVED_FROM = "derived_from"
    QUOTES = "quotes"
    SUMMARIZES = "summarizes"
    TRANSFORMS = "transforms"
    GENERATED_FROM = "generated_from"
    CONTAINS = "contains"


# Typed endpoint vocabulary for the source-ingestion subgraph (ch05 core tables).
NODE_TYPE_SOURCE = "source"
NODE_TYPE_SOURCE_VERSION = "source_version"
NODE_TYPE_CANONICAL_DOCUMENT = "canonical_document"
NODE_TYPE_BLOB = "blob"
