"""
Blob adapters (FND-06): the filesystem BlobStore + the PostgreSQL bookkeeping.

The filesystem store runs the crash-consistent finalize protocol (ch19); the
repository commits blob_objects/blob_references (T3 schema, unmodified).
"""

from milpbooklm_adapters.blobs.filesystem_store import FilesystemBlobStore
from milpbooklm_adapters.blobs.pg_repository import PgBlobRepository

__all__ = [
    "FilesystemBlobStore",
    "PgBlobRepository",
]
