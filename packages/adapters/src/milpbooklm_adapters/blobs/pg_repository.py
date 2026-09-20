"""
PostgreSQL blob bookkeeping (FND-06): the blob_objects + blob_references tables.

``commit_finalized`` is the single DB write of the put protocol - object row and
reference in ONE transaction, executed strictly after the filesystem finalize.
The table's load-bearing constraints are honored: ``ck_blob_objects_state``
(staging/finalized/purged), ``ck_blob_objects_finalized_timestamp`` (state
finalized iff finalized_at is set), and the (blob_id, referrer_kind,
referrer_id) reference uniqueness (committed idempotently). The FND-03
finalize-guard trigger makes the ``finalized`` state terminal in the database,
so this adapter never mutates a finalized row (GC deletes the file, not the
record).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from milpbooklm_application.blob_store import BlobIntegrityError
from milpbooklm_domain.blobs import BlobObject, BlobState
from sqlalchemy.dialects.postgresql import insert as pg_insert

from milpbooklm_adapters.db.tables.blobs import blob_objects, blob_references


class PgBlobRepository:
    """The blob_objects/blob_references bookkeeping adapter."""

    def __init__(self, engine: sa.engine.Engine) -> None:
        """Wire the engine."""
        self._engine = engine

    def commit_finalized(
        self,
        *,
        content_sha256: str,
        size_bytes: int,
        storage_path: str,
        finalized_at: datetime,
        content_type: str | None = None,
        referrer_kind: str | None = None,
        referrer_id: uuid.UUID | None = None,
    ) -> BlobObject:
        """Commit the finalized object (and its reference) in one transaction."""
        with self._engine.begin() as conn:
            existing = conn.execute(
                sa.select(blob_objects.c.id, blob_objects.c.state, blob_objects.c.size_bytes).where(
                    blob_objects.c.content_sha256 == content_sha256
                )
            ).first()
            if existing is not None:
                if existing.size_bytes != size_bytes:
                    raise BlobIntegrityError(
                        f"blob_objects row for {content_sha256} records "
                        f"{existing.size_bytes} bytes, the object is {size_bytes}"
                    )
                # Content addressing: reuse the row, completing a stale staging
                # row (a crashed earlier writer) or re-finalizing a purged one.
                if existing.state != BlobState.FINALIZED.value:
                    conn.execute(
                        sa.update(blob_objects)
                        .where(blob_objects.c.id == existing.id)
                        .values(state=BlobState.FINALIZED.value, finalized_at=finalized_at)
                    )
                blob_id = existing.id
            else:
                blob_id = conn.execute(
                    sa.insert(blob_objects)
                    .values(
                        content_sha256=content_sha256,
                        size_bytes=size_bytes,
                        content_type=content_type,
                        storage_path=storage_path,
                        state=BlobState.FINALIZED.value,
                        finalized_at=finalized_at,
                    )
                    .returning(blob_objects.c.id)
                ).scalar_one()
            if referrer_kind is not None and referrer_id is not None:
                # Idempotent: the unique (blob_id, referrer_kind, referrer_id)
                # constraint absorbs duplicate commits of the same reference.
                conn.execute(
                    pg_insert(blob_references)
                    .values(
                        blob_id=blob_id,
                        referrer_kind=referrer_kind,
                        referrer_id=referrer_id,
                    )
                    .on_conflict_do_nothing()
                )
            row = conn.execute(
                sa.select(blob_objects).where(blob_objects.c.id == blob_id)
            ).first()
        if row is None:
            # Unreachable: the row was just inserted or updated in this
            # transaction; the check keeps the port's BlobObject return exact.
            raise RuntimeError(f"blob row {blob_id} is absent after its commit")
        return self._object_from_row(row)

    def get(self, blob_id: uuid.UUID) -> BlobObject | None:
        """Return the object record, or None."""
        with self._engine.begin() as conn:
            row = conn.execute(
                sa.select(blob_objects).where(blob_objects.c.id == blob_id)
            ).first()
        return self._object_from_row(row) if row is not None else None

    def all_objects(self) -> list[BlobObject]:
        """All object records (reconciliation scans every lifecycle state)."""
        with self._engine.begin() as conn:
            rows = conn.execute(
                sa.select(blob_objects).order_by(blob_objects.c.created_at)
            ).all()
        return [self._object_from_row(row) for row in rows]

    def reference_counts(self) -> dict[uuid.UUID, int]:
        """Return reference counts per blob id (blobs without references are absent)."""
        with self._engine.begin() as conn:
            rows = conn.execute(
                sa.select(blob_references.c.blob_id, sa.func.count())
                .group_by(blob_references.c.blob_id)
            ).all()
        return {row.blob_id: int(row[1]) for row in rows}

    @staticmethod
    def _object_from_row(row: sa.engine.Row[Any]) -> BlobObject:
        """Build the domain value from a blob_objects row."""
        return BlobObject(
            id=row.id,
            content_sha256=row.content_sha256,
            size_bytes=row.size_bytes,
            content_type=row.content_type,
            storage_path=row.storage_path,
            state=BlobState(row.state),
            finalized_at=row.finalized_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
