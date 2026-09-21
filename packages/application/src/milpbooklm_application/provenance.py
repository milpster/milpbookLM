"""
Provenance traversal and effective-restriction computation (ch07, ING-01c).

Edges read "from_node <edge_type> to_node", so ancestor traversal follows each
edge's `to` endpoint. Traversal is bounded (depth) and cycle-safe (visited set),
works on the normalized rows only, and never infers relationships from vector
similarity. Effective restrictions union the deny/reuse/export rows across the
version and its content-bearing ancestors and are cached only with all
policy/version inputs in the key.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from milpbooklm_domain.provenance import ProvenanceEdgeType

# Depth bound for ancestor walks: a source-ingestion chain (canonical document ->
# source version -> blob, plus refresh re-derivations) is far shorter; the bound
# exists so a corrupt/cyclic graph can never loop the traversal (ch07).
MAX_PROVENANCE_DEPTH: Final[int] = 8

ProvenanceNodeKey = tuple[str, uuid.UUID, uuid.UUID | None]


@dataclass(frozen=True, slots=True)
class ProvenanceNode:
    """One typed provenance endpoint (type + id + optional version)."""

    node_type: str
    node_id: uuid.UUID
    version_id: uuid.UUID | None = None

    @property
    def key(self) -> ProvenanceNodeKey:
        """Identity used for the cycle-safe visited bookkeeping."""
        return (self.node_type, self.node_id, self.version_id)


@dataclass(frozen=True, slots=True)
class ProvenanceEdge:
    """One normalized provenance row, reading "from_node <edge_type> to_node"."""

    from_node: ProvenanceNode
    edge_type: ProvenanceEdgeType
    to_node: ProvenanceNode
    locator: dict[str, object] | None = None
    transform_identity: str | None = None
    transform_version: str | None = None
    confidence: float | None = None


OutgoingResolver = Callable[[tuple[ProvenanceNode, ...]], tuple[ProvenanceEdge, ...]]


def bounded_ancestor_traversal(
    start: ProvenanceNode,
    outgoing: OutgoingResolver,
    max_depth: int = MAX_PROVENANCE_DEPTH,
) -> tuple[ProvenanceEdge, ...]:
    """
    Walk ancestor edges from `start` with a depth bound and a visited set.

    Each round resolves the outgoing edges of the current frontier; endpoints
    already visited are dropped (cycle safety) and the walk stops after
    `max_depth` rounds (bounded). Returns the traversed edges in round order.
    """
    visited: set[ProvenanceNodeKey] = {start.key}
    frontier: tuple[ProvenanceNode, ...] = (start,)
    traversed: list[ProvenanceEdge] = []
    for _ in range(max_depth):
        if not frontier:
            break
        edges = outgoing(frontier)
        traversed.extend(edges)
        next_frontier = [
            edge.to_node for edge in edges if edge.to_node.key not in visited
        ]
        visited.update(node.key for node in next_frontier)
        frontier = tuple(next_frontier)
    return tuple(traversed)


@dataclass(frozen=True, slots=True)
class RestrictionInputs:
    """
    Every policy/version input an effective-restriction result depends on.

    All fields participate in the cache key, so a cached result can never
    outlive its inputs: any restriction-row, source-revision, policy, or
    ancestor-set change yields a different key (ch07: "cached only with all
    policy/version inputs in the key").
    """

    source_version_id: uuid.UUID
    user_id: uuid.UUID
    source_revision: int
    restriction_policy: str | None
    ancestor_version_ids: tuple[uuid.UUID, ...]
    restriction_rows: tuple[tuple[str, uuid.UUID | None, str], ...]


@dataclass(frozen=True, slots=True)
class EffectiveRestrictions:
    """The deny/reuse/export restrictions effective for one user on one version."""

    restriction_types: tuple[str, ...]

    def denies(self, restriction_type: str) -> bool:
        """Whether one closed-set restriction type applies."""
        return restriction_type in self.restriction_types


def compute_effective_restrictions(inputs: RestrictionInputs) -> EffectiveRestrictions:
    """
    Union of matching rows across the version and its content-bearing ancestors.

    A row matches when it names no user (applies to everyone) or names the
    requesting user. The source's restriction policy is carried in the key as
    policy input; in v1 it adds no denials of its own (local imports create
    zero restriction rows, T12).
    """
    applicable = sorted(
        {
            row_type
            for row_type, row_user, _created_at in inputs.restriction_rows
            if row_user is None or row_user == inputs.user_id
        }
    )
    return EffectiveRestrictions(restriction_types=tuple(applicable))


class EffectiveRestrictionCache:
    """
    Process-local memoization keyed on the complete RestrictionInputs.

    The key carries every policy/version input, so a stale entry is impossible
    by construction; the entry bound only caps memory.
    """

    def __init__(self, max_entries: int = 256) -> None:
        """Bound the memoization table."""
        self._max_entries = max_entries
        self._entries: dict[RestrictionInputs, EffectiveRestrictions] = {}

    def get(self, inputs: RestrictionInputs) -> EffectiveRestrictions | None:
        """Return the cached result for exactly these inputs, if present."""
        return self._entries.get(inputs)

    def put(self, inputs: RestrictionInputs, result: EffectiveRestrictions) -> None:
        """Memoize a result, evicting the oldest entry past the bound."""
        if inputs not in self._entries and len(self._entries) >= self._max_entries:
            oldest = next(iter(self._entries))
            del self._entries[oldest]
        self._entries[inputs] = result
