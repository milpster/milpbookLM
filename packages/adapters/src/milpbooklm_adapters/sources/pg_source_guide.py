"""
Deterministic Source Guide and effective-restriction reads (ING-01c, ch07/ch05).

The guide is metadata-only (display title, source type, version, restrictions)
and never infers content. Effective restrictions union the deny/reuse/export
rows across the active version and its content-bearing ancestors, computed by
bounded cycle-safe traversal over provenance edges (never vector similarity)
and cached only with every policy/version input in the key.
"""

from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from milpbooklm_application.provenance import (
    EffectiveRestrictionCache,
    EffectiveRestrictions,
    ProvenanceEdge,
    ProvenanceNode,
    RestrictionInputs,
    bounded_ancestor_traversal,
    compute_effective_restrictions,
)
from milpbooklm_application.source_acquisition import SourceGuideView, SourceNotFoundError
from milpbooklm_domain.provenance import (
    NODE_TYPE_SOURCE_VERSION,
    ProvenanceEdgeType,
)
from sqlalchemy.engine import Connection

from milpbooklm_adapters.db.tables.collaboration import notebook_memberships
from milpbooklm_adapters.db.tables.sources import (
    canonical_documents,
    provenance_edges,
    source_restrictions,
    source_versions,
    sources,
)


class SourceGuideStore:
    """Guide rendering and cached effective-restriction computation."""

    def __init__(self, engine: sa.engine.Engine) -> None:
        """Bind the application-role engine and the restriction memoization."""
        self._engine = engine
        self._restrictions_cache = EffectiveRestrictionCache()

    def guide(self, source_id: uuid.UUID, actor_id: uuid.UUID) -> SourceGuideView | None:
        """Render metadata-only guide fields without model inference."""
        with self._engine.begin() as connection:
            row = connection.execute(
                sa.select(
                    sources.c.id.label("source_id"),
                    sources.c.display_title,
                    sources.c.type,
                    source_versions.c.id.label("source_version_id"),
                    source_versions.c.version_number,
                )
                .join(source_versions, source_versions.c.id == sources.c.current_version_id)
                .join(
                    canonical_documents,
                    canonical_documents.c.source_version_id == source_versions.c.id,
                )
                .where(
                    sources.c.id == source_id,
                    canonical_documents.c.active.is_(True),
                    source_versions.c.status == "active",
                    sources.c.notebook_id.in_(
                        sa.select(notebook_memberships.c.notebook_id).where(
                            notebook_memberships.c.user_id == actor_id
                        )
                    ),
                )
            ).mappings().first()
        if row is None:
            return None
        try:
            restrictions = self.effective_restrictions(source_id, actor_id)
        except SourceNotFoundError:
            return None
        source_type = str(row["type"]).replace("_", " ")
        return SourceGuideView(
            source_id=row["source_id"],
            source_version_id=row["source_version_id"],
            summary=(
                f"{row['display_title']} is an active {source_type} source "
                f"(version {row['version_number']})."
            ),
            labels=(source_type, "active", "canonical"),
            restrictions=restrictions.restriction_types,
        )

    def effective_restrictions(
        self, source_id: uuid.UUID, actor_id: uuid.UUID
    ) -> EffectiveRestrictions:
        """Effective deny/reuse/export state across content-bearing ancestors."""
        with self._engine.begin() as connection:
            active = connection.execute(
                sa.select(
                    sources.c.revision,
                    sources.c.restriction_policy,
                    source_versions.c.id.label("active_version_id"),
                )
                .join(source_versions, source_versions.c.id == sources.c.current_version_id)
                .where(
                    sources.c.id == source_id,
                    source_versions.c.status == "active",
                    sources.c.notebook_id.in_(
                        sa.select(notebook_memberships.c.notebook_id).where(
                            notebook_memberships.c.user_id == actor_id
                        )
                    ),
                )
            ).mappings().first()
            if active is None:
                raise SourceNotFoundError
            active_version = active["active_version_id"]
            ancestors = self._ancestor_source_versions(connection, active_version)
            rows = connection.execute(
                sa.select(
                    source_restrictions.c.restriction_type,
                    source_restrictions.c.user_id,
                    source_restrictions.c.created_at,
                )
                .where(
                    source_restrictions.c.source_version_id.in_([active_version, *ancestors]),
                    sa.or_(
                        source_restrictions.c.user_id.is_(None),
                        source_restrictions.c.user_id == actor_id,
                    ),
                )
                .order_by(
                    source_restrictions.c.created_at,
                    source_restrictions.c.restriction_type,
                    source_restrictions.c.user_id,
                )
            ).mappings().all()
        inputs = RestrictionInputs(
            source_version_id=active_version,
            user_id=actor_id,
            source_revision=active["revision"],
            restriction_policy=_canonical_policy(active["restriction_policy"]),
            ancestor_version_ids=(active_version, *ancestors),
            restriction_rows=tuple(
                (row["restriction_type"], row["user_id"], row["created_at"].isoformat())
                for row in rows
            ),
        )
        cached = self._restrictions_cache.get(inputs)
        if cached is not None:
            return cached
        computed = compute_effective_restrictions(inputs)
        self._restrictions_cache.put(inputs, computed)
        return computed

    def _ancestor_source_versions(
        self, connection: Connection, start_version_id: uuid.UUID
    ) -> tuple[uuid.UUID, ...]:
        """Content-bearing source-version ancestors (bounded, cycle-safe)."""
        edges = bounded_ancestor_traversal(
            ProvenanceNode(NODE_TYPE_SOURCE_VERSION, start_version_id),
            lambda frontier: self._frontier_edges(connection, frontier),
        )
        return tuple(
            edge.to_node.node_id
            for edge in edges
            if edge.to_node.node_type == NODE_TYPE_SOURCE_VERSION
        )

    def _frontier_edges(
        self, connection: Connection, frontier: tuple[ProvenanceNode, ...]
    ) -> tuple[ProvenanceEdge, ...]:
        """One query per traversal round: outgoing edges of the frontier only."""
        pairs = [(node.node_type, node.node_id) for node in frontier]
        rows = connection.execute(
            sa.select(provenance_edges)
            .where(
                sa.tuple_(provenance_edges.c.from_type, provenance_edges.c.from_id).in_(
                    pairs
                )
            )
            .order_by(provenance_edges.c.created_at, provenance_edges.c.id)
        ).mappings().all()
        return tuple(
            ProvenanceEdge(
                from_node=ProvenanceNode(
                    str(row["from_type"]), row["from_id"], row["from_version_id"]
                ),
                edge_type=ProvenanceEdgeType(row["edge_type"]),
                to_node=ProvenanceNode(
                    str(row["to_type"]), row["to_id"], row["to_version_id"]
                ),
                locator=row["locator"],
                transform_identity=row["transform_identity"],
                transform_version=row["transform_version"],
                confidence=None
                if row["confidence"] is None
                else float(row["confidence"]),
            )
            for row in rows
        )


def _canonical_policy(policy: object) -> str | None:
    """Canonical JSON form of the source policy for the restriction cache key."""
    if policy is None:
        return None
    return json.dumps(policy, sort_keys=True)
