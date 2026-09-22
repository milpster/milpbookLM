"""PostgreSQL identity-closure implementation of AD-016 source purge."""

# noqa: SIZE_OK - one transactional identity-closure state machine; splitting it would
# hide ordering dependencies between tombstones, immutable derivatives, and blob references.

from __future__ import annotations

import uuid
from typing import Final

import sqlalchemy as sa
from milpbooklm_application.blob_store import BlobStore
from milpbooklm_application.source_lifecycle import (
    BackupExpiryScheduler,
    PurgeMark,
    PurgePreview,
    PurgeReport,
)

from milpbooklm_adapters.db.tables.blobs import blob_objects, blob_references, purge_tasks
from milpbooklm_adapters.db.tables.collaboration import notebook_memberships
from milpbooklm_adapters.db.tables.conversation import messages
from milpbooklm_adapters.db.tables.indexing import index_generations
from milpbooklm_adapters.db.tables.manifests import (
    generation_input_manifests,
    generation_manifest_items,
)
from milpbooklm_adapters.db.tables.ops import jobs
from milpbooklm_adapters.db.tables.sources import (
    canonical_documents,
    provenance_edges,
    source_versions,
    sources,
)
from milpbooklm_adapters.db.tables.studio import (
    artifact_versions,
    artifacts,
    study_session_snapshots,
    user_artifact_state,
)

_CAVEAT: Final = (
    "Controlled copies were erased; data already transmitted to external services or "
    "independent manual copies with severed provenance cannot be recalled."
)


class PgSourcePurge:
    """Discover dependencies by stable IDs, tombstone synchronously, erase asynchronously."""

    def __init__(
        self,
        engine: sa.engine.Engine,
        backup_expiry: BackupExpiryScheduler,
        blobs: BlobStore,
    ) -> None:
        """Bind persistence, backup-expiry, and controlled-blob ports."""
        self._engine = engine
        self._backup_expiry = backup_expiry
        self._blobs = blobs

    def preview(self, source_id: uuid.UUID, actor_id: uuid.UUID) -> PurgePreview | None:
        """Count the source's identity closure without reading content."""
        with self._engine.begin() as connection:
            if not self._authorized(connection, source_id, actor_id):
                return None
            counts = self._counts(connection, source_id)
        return PurgePreview(source_id=source_id, counts=counts)

    def mark(self, source_id: uuid.UUID, actor_id: uuid.UUID) -> PurgeMark | None:
        """Block access and persist the purge task in one transaction."""
        task_id = uuid.uuid4()
        with self._engine.begin() as connection:
            if not self._authorized(connection, source_id, actor_id, lock=True):
                return None
            counts = self._counts(connection, source_id)
            version_ids, manifest_ids = self._identity_sets(connection, source_id)
            connection.execute(
                sa.update(sources)
                .where(sources.c.id == source_id)
                .values(
                    availability="deleted_tombstoned",
                    current_version_id=None,
                    updated_at=sa.func.now(),
                )
            )
            connection.execute(
                sa.update(source_versions)
                .where(source_versions.c.id.in_(version_ids))
                .values(status="tombstoned", tombstoned_at=sa.func.now())
            )
            if manifest_ids:
                connection.execute(
                    sa.update(messages)
                    .where(messages.c.manifest_id.in_(manifest_ids))
                    .values(tombstone_at=sa.func.now(), tombstone_reason="source_purged")
                )
            connection.execute(
                sa.insert(purge_tasks).values(
                    id=task_id,
                    subject_kind="source",
                    subject_id=source_id,
                    initiated_by_user_id=actor_id,
                    progress={
                        "phase": "marked",
                        "counts": dict(counts),
                        "caveat": _CAVEAT,
                    },
                )
            )
        self._backup_expiry.schedule_source_expiry(source_id, task_id)
        return PurgeMark(task_id=task_id, source_id=source_id, counts=counts)

    def erase(self, task_id: uuid.UUID) -> PurgeReport:
        """Erase marked derivatives and unreferenced controlled blobs."""
        with self._engine.begin() as connection:
            task = (
                connection.execute(
                    sa.select(purge_tasks).where(purge_tasks.c.id == task_id).with_for_update()
                )
                .mappings()
                .one()
            )
            source_id = uuid.UUID(str(task["subject_id"]))
            connection.execute(
                sa.update(purge_tasks)
                .where(purge_tasks.c.id == task_id)
                .values(
                    status="running",
                    started_at=sa.func.coalesce(purge_tasks.c.started_at, sa.func.now()),
                )
            )
            version_ids, manifest_ids = self._identity_sets(connection, source_id)
            document_ids = tuple(
                connection.execute(
                    sa.select(canonical_documents.c.id).where(
                        canonical_documents.c.source_version_id.in_(version_ids)
                    )
                ).scalars()
            )
            artifact_version_ids = (
                tuple(
                    connection.execute(
                        sa.select(artifact_versions.c.id).where(
                            artifact_versions.c.manifest_id.in_(manifest_ids)
                        )
                    ).scalars()
                )
                if manifest_ids
                else ()
            )
            connection.execute(sa.text("SELECT set_config('milpbooklm.purge_context', 'on', true)"))
            erased: list[tuple[str, int]] = []
            erased.append(
                (
                    "messages",
                    self._delete(connection, messages, messages.c.manifest_id.in_(manifest_ids))
                    if manifest_ids
                    else 0,
                )
            )
            erased.append(
                (
                    "study_session_snapshots",
                    self._delete(
                        connection,
                        study_session_snapshots,
                        study_session_snapshots.c.artifact_version_id.in_(artifact_version_ids),
                    )
                    if artifact_version_ids
                    else 0,
                )
            )
            erased.append(
                (
                    "user_artifact_state",
                    self._delete(
                        connection,
                        user_artifact_state,
                        user_artifact_state.c.artifact_version_id.in_(artifact_version_ids),
                    )
                    if artifact_version_ids
                    else 0,
                )
            )
            erased.append(
                (
                    "artifact_versions",
                    self._delete(
                        connection,
                        artifact_versions,
                        artifact_versions.c.id.in_(artifact_version_ids),
                    )
                    if artifact_version_ids
                    else 0,
                )
            )
            erased.append(("artifacts", self._delete_orphan_artifacts(connection)))
            erased.append(
                (
                    "manifest_items",
                    self._delete(
                        connection,
                        generation_manifest_items,
                        generation_manifest_items.c.manifest_id.in_(manifest_ids),
                    )
                    if manifest_ids
                    else 0,
                )
            )
            erased.append(
                (
                    "manifests",
                    self._delete(
                        connection,
                        generation_input_manifests,
                        generation_input_manifests.c.id.in_(manifest_ids),
                    )
                    if manifest_ids
                    else 0,
                )
            )
            erased.append(
                (
                    "index_generations",
                    self._delete(
                        connection, index_generations, index_generations.c.source_id == source_id
                    ),
                )
            )
            job_predicate = sa.or_(
                jobs.c.payload["params"]["source_id"].astext == str(source_id),
                jobs.c.payload["params"]["source_version_id"].astext.in_(
                    tuple(str(item) for item in version_ids)
                ),
            )
            erased.append(("jobs", self._delete(connection, jobs, job_predicate)))
            edge_filter = sa.or_(
                provenance_edges.c.from_id == source_id,
                provenance_edges.c.to_id == source_id,
                provenance_edges.c.from_version_id.in_(version_ids),
                provenance_edges.c.to_version_id.in_(version_ids),
                provenance_edges.c.from_id.in_(document_ids),
                provenance_edges.c.to_id.in_(document_ids),
            )
            erased.append(
                ("provenance_edges", self._delete(connection, provenance_edges, edge_filter))
            )
            erased.append(
                (
                    "canonical_documents",
                    self._delete(
                        connection, canonical_documents, canonical_documents.c.id.in_(document_ids)
                    )
                    if document_ids
                    else 0,
                )
            )
            source_blob_ids = tuple(
                connection.execute(
                    sa.select(blob_references.c.blob_id).where(
                        blob_references.c.referrer_kind == "source_version",
                        blob_references.c.referrer_id.in_(version_ids),
                    )
                ).scalars()
            )
            artifact_blob_ids = (
                tuple(
                    connection.execute(
                        sa.select(blob_references.c.blob_id).where(
                            blob_references.c.referrer_kind.in_(
                                ("artifact_version", "artifact_rendition")
                            ),
                            blob_references.c.referrer_id.in_(artifact_version_ids),
                        )
                    ).scalars()
                )
                if artifact_version_ids
                else ()
            )
            blob_ids = (*source_blob_ids, *artifact_blob_ids)
            erased.append(
                (
                    "blob_references",
                    self._delete(
                        connection,
                        blob_references,
                        sa.and_(
                            blob_references.c.referrer_kind == "source_version",
                            blob_references.c.referrer_id.in_(version_ids),
                        ),
                    ),
                )
            )
            erased.append(
                (
                    "artifact_blob_references",
                    self._delete(
                        connection,
                        blob_references,
                        sa.and_(
                            blob_references.c.referrer_kind.in_(
                                ("artifact_version", "artifact_rendition")
                            ),
                            blob_references.c.referrer_id.in_(artifact_version_ids),
                        ),
                    )
                    if artifact_version_ids
                    else 0,
                )
            )
            connection.execute(
                sa.update(source_versions)
                .where(source_versions.c.id.in_(version_ids))
                .values(
                    original_blob_id=None,
                    content_sha256=sa.literal("purged:") + sa.cast(source_versions.c.id, sa.Text),
                    content_size_bytes=None,
                )
            )
            unreferenced = (
                tuple(
                    connection.execute(
                        sa.select(blob_objects.c.id, blob_objects.c.content_sha256).where(
                            blob_objects.c.id.in_(blob_ids),
                            ~sa.exists().where(blob_references.c.blob_id == blob_objects.c.id),
                        )
                    ).all()
                )
                if blob_ids
                else ()
            )
            unreferenced_ids = tuple(row.id for row in unreferenced)
            if unreferenced_ids:
                connection.execute(
                    sa.update(blob_objects)
                    .where(blob_objects.c.id.in_(unreferenced_ids))
                    .values(state="purged", finalized_at=None, updated_at=sa.func.now())
                )
            progress = {"phase": "erasing_blobs", "erased": dict(erased), "caveat": _CAVEAT}
            connection.execute(
                sa.update(purge_tasks).where(purge_tasks.c.id == task_id).values(progress=progress)
            )
        for row in unreferenced:
            self._blobs.delete_final(str(row.content_sha256))
        with self._engine.begin() as connection:
            connection.execute(sa.text("SELECT set_config('milpbooklm.purge_context', 'on', true)"))
            blob_count = (
                self._delete(
                    connection,
                    blob_objects,
                    blob_objects.c.id.in_(unreferenced_ids),
                )
                if unreferenced_ids
                else 0
            )
            erased.append(("blob_objects", blob_count))
            progress = {"phase": "completed", "erased": dict(erased), "caveat": _CAVEAT}
            connection.execute(
                sa.update(purge_tasks)
                .where(purge_tasks.c.id == task_id)
                .values(status="completed", progress=progress, finished_at=sa.func.now())
            )
        return PurgeReport(task_id, source_id, tuple(erased), _CAVEAT)

    @staticmethod
    def _delete(
        connection: sa.Connection, table: sa.Table, predicate: sa.ColumnElement[bool]
    ) -> int:
        return connection.execute(sa.delete(table).where(predicate)).rowcount

    @staticmethod
    def _delete_orphan_artifacts(connection: sa.Connection) -> int:
        return connection.execute(
            sa.delete(artifacts).where(
                ~sa.exists().where(artifact_versions.c.artifact_id == artifacts.c.id)
            )
        ).rowcount

    @staticmethod
    def _authorized(
        connection: sa.Connection,
        source_id: uuid.UUID,
        actor_id: uuid.UUID,
        *,
        lock: bool = False,
    ) -> bool:
        query = (
            sa.select(sources.c.id)
            .join(
                notebook_memberships,
                notebook_memberships.c.notebook_id == sources.c.notebook_id,
            )
            .where(
                sources.c.id == source_id,
                notebook_memberships.c.user_id == actor_id,
            )
        )
        if lock:
            query = query.with_for_update(of=sources)
        return connection.execute(query).first() is not None

    @staticmethod
    def _identity_sets(
        connection: sa.Connection, source_id: uuid.UUID
    ) -> tuple[tuple[uuid.UUID, ...], tuple[uuid.UUID, ...]]:
        version_ids = tuple(
            connection.execute(
                sa.select(source_versions.c.id).where(source_versions.c.source_id == source_id)
            ).scalars()
        )
        document_ids = tuple(
            connection.execute(
                sa.select(canonical_documents.c.id).where(
                    canonical_documents.c.source_version_id.in_(version_ids)
                )
            ).scalars()
        )
        manifest_ids = tuple(
            connection.execute(
                sa.select(generation_manifest_items.c.manifest_id)
                .where(
                    sa.or_(
                        sa.and_(
                            generation_manifest_items.c.item_kind == "source_version",
                            generation_manifest_items.c.item_id.in_(version_ids),
                        ),
                        sa.and_(
                            generation_manifest_items.c.item_kind == "canonical_document",
                            generation_manifest_items.c.item_id.in_(document_ids),
                        ),
                    )
                )
                .distinct()
            ).scalars()
        )
        return version_ids, manifest_ids

    def _counts(
        self, connection: sa.Connection, source_id: uuid.UUID
    ) -> tuple[tuple[str, int], ...]:
        version_ids, manifest_ids = self._identity_sets(connection, source_id)
        return (
            ("source_versions", len(version_ids)),
            ("manifests", len(manifest_ids)),
            (
                "messages",
                self._count(connection, messages, messages.c.manifest_id.in_(manifest_ids))
                if manifest_ids
                else 0,
            ),
            (
                "artifact_versions",
                self._count(
                    connection, artifact_versions, artifact_versions.c.manifest_id.in_(manifest_ids)
                )
                if manifest_ids
                else 0,
            ),
            (
                "index_generations",
                self._count(
                    connection, index_generations, index_generations.c.source_id == source_id
                ),
            ),
        )

    @staticmethod
    def _count(
        connection: sa.Connection, table: sa.Table, predicate: sa.ColumnElement[bool]
    ) -> int:
        return int(
            connection.scalar(sa.select(sa.func.count()).select_from(table).where(predicate)) or 0
        )
