"""
Table modules for the ch05 schema (FND-03).

Import order is irrelevant: all tables share one MetaData and create_all
resolves FK ordering.
"""

from . import (
    blobs,
    collaboration,
    conversation,
    identity,
    indexing,
    manifests,
    ops,
    providers,
    research,
    sources,
    studio,
)

__all__ = [
    "blobs",
    "collaboration",
    "conversation",
    "identity",
    "indexing",
    "manifests",
    "ops",
    "providers",
    "research",
    "sources",
    "studio",
]
