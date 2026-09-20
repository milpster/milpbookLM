"""
Public contracts (OpenAPI, JSON Schema, event and provider descriptors).

Plain data only: no framework imports (TAD-009: OpenAPI 3.1 + versioned JSON Schema).
"""

from milpbooklm_contracts.canonical_document import (
    AuthorityClass,
    CanonicalDocument,
    CanonicalNode,
    NodeKind,
    ParserDescriptor,
    SourceLocator,
    canonical_chunk_id,
    canonical_document_id,
    canonical_node_id,
)
from milpbooklm_contracts.identity import IdempotencyKey, RequestId

__all__ = [
    "AuthorityClass",
    "CanonicalDocument",
    "CanonicalNode",
    "IdempotencyKey",
    "NodeKind",
    "ParserDescriptor",
    "RequestId",
    "SourceLocator",
    "canonical_chunk_id",
    "canonical_document_id",
    "canonical_node_id",
]
