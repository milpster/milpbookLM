"""
Provenance edge persistence for source activation (ING-01c, ch07).

The activation transaction records the normalized provenance rows for the
promoted version: the source contains its version, the version derives from
its content blob, and the canonical document is generated from the version by
the named parser. Re-inserting the same row is a no-op, which keeps a
re-run of an already-activated source idempotent.
"""

from __future__ import annotations

import uuid

from milpbooklm_domain.provenance import (
    NODE_TYPE_BLOB,
    NODE_TYPE_CANONICAL_DOCUMENT,
    NODE_TYPE_SOURCE,
    NODE_TYPE_SOURCE_VERSION,
    ProvenanceEdgeType,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection, RowMapping

from milpbooklm_adapters.db.tables.sources import provenance_edges

# The 10-column identity unique index (uq_provenance_edges_identity):
# re-inserting the same provenance row is a no-op, which keeps activation
# idempotent under re-runs.
_EDGE_CONFLICT_TARGET = (
    "from_type", "from_id", "from_version_id", "edge_type", "to_type", "to_id",
    "to_version_id", "locator", "transform_identity", "transform_version",
)


def insert_activation_edges(
    connection: Connection,
    source_id: uuid.UUID,
    version: RowMapping,
    document: RowMapping,
) -> None:
    """Record the activation provenance rows (idempotent under re-runs)."""
    edges: list[dict[str, object]] = [
        {
            "from_type": NODE_TYPE_SOURCE,
            "from_id": source_id,
            "edge_type": ProvenanceEdgeType.CONTAINS.value,
            "to_type": NODE_TYPE_SOURCE_VERSION,
            "to_id": version["id"],
        },
    ]
    if version["original_blob_id"] is not None:
        edges.append(
            {
                "from_type": NODE_TYPE_SOURCE_VERSION,
                "from_id": version["id"],
                "edge_type": ProvenanceEdgeType.DERIVED_FROM.value,
                "to_type": NODE_TYPE_BLOB,
                "to_id": version["original_blob_id"],
            }
        )
    edges.append(
        {
            "from_type": NODE_TYPE_CANONICAL_DOCUMENT,
            "from_id": document["id"],
            "edge_type": ProvenanceEdgeType.GENERATED_FROM.value,
            "to_type": NODE_TYPE_SOURCE_VERSION,
            "to_id": version["id"],
            "transform_identity": document["parser_identity"],
            "transform_version": document["parser_version"],
            "confidence": 1.0,
        }
    )
    for edge in edges:
        connection.execute(
            pg_insert(provenance_edges)
            .values(**edge)
            .on_conflict_do_nothing(index_elements=list(_EDGE_CONFLICT_TARGET))
        )
