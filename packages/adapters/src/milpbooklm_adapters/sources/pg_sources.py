"""PostgreSQL source catalog with notebook-scoped identity and blob references."""

from __future__ import annotations

import uuid
from typing import Final

import sqlalchemy as sa
from milpbooklm_application.provenance import EffectiveRestrictions
from milpbooklm_application.source_acquisition import (
    IMPORTER_VERSION,
    AcquireSourceCommand,
    SourceCatalog,
    SourceConflictError,
    SourceGuideView,
    SourceNotFoundError,
    SourceView,
)
from milpbooklm_domain.blobs import BlobObject
from milpbooklm_domain.sources import Availability, SourceType
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import RowMapping

from milpbooklm_adapters.db.tables.blobs import blob_references
from milpbooklm_adapters.db.tables.collaboration import notebook_memberships
from milpbooklm_adapters.db.tables.sources import (
    canonical_documents,
    canonical_nodes,
    source_versions,
    sources,
)

from .pg_source_activation import SourceActivationStore
from .pg_source_guide import SourceGuideStore

_SOURCE_TYPES: Final = {
    "application/pdf": SourceType.PDF,
    "text/plain": SourceType.PLAIN_TEXT,
    "text/markdown": SourceType.MARKDOWN,
    "text/csv": SourceType.CSV,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": SourceType.XLSX,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": SourceType.DOCX,
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": SourceType.PPTX,
    "application/epub+zip": SourceType.EPUB,
    "text/html": SourceType.WEB_URL,
    "image/png": SourceType.IMAGE,
    "image/jpeg": SourceType.IMAGE,
    "image/gif": SourceType.IMAGE,
    "image/webp": SourceType.IMAGE,
    "image/bmp": SourceType.IMAGE,
    "audio/x-wav": SourceType.AUDIO,
    "audio/mpeg": SourceType.AUDIO,
    "video/mp4": SourceType.VIDEO,
    "video/webm": SourceType.VIDEO,
}

_CANONICAL_ROOT_NODE_ID: Final = (
    sa.select(canonical_nodes.c.id)
    .join(
        canonical_documents,
        canonical_documents.c.id == canonical_nodes.c.canonical_document_id,
    )
    .where(
        canonical_documents.c.source_version_id == source_versions.c.id,
        canonical_documents.c.active.is_(True),
        canonical_nodes.c.parent_node_id.is_(None),
    )
    .order_by(canonical_nodes.c.seq)
    .limit(1)
    .correlate(source_versions)
    .scalar_subquery()
)


class PgSourceCatalog(SourceCatalog):
    """Persist source ownership separately from globally deduplicated blobs."""

    def __init__(self, engine: sa.engine.Engine) -> None:
        """Wire the PostgreSQL engine, the activation store, and the guide store."""
        self._engine = engine
        self._activation = SourceActivationStore(engine)
        self._guide = SourceGuideStore(engine)

    def acquire(self, command: AcquireSourceCommand, blob: BlobObject) -> tuple[SourceView, bool]:
        """Create or return the notebook-local source for this acquisition identity."""
        if command.refresh_source_id is not None:
            return self._acquire_refresh(command, blob)
        origin = self._origin(command, blob)
        source_type = self._source_type(blob)
        with self._engine.begin() as connection:
            connection.execute(
                sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"),
                {"identity": f"{command.notebook_id}:{origin}"},
            )
            existing = connection.execute(
                self._select_view().where(
                    sources.c.notebook_id == command.notebook_id,
                    sources.c.origin == origin,
                )
            ).mappings().first()
            if existing is not None:
                return self._view(existing), False
            source_id = uuid.uuid4()
            version_id = uuid.uuid4()
            connection.execute(
                sa.insert(sources).values(
                    id=source_id,
                    notebook_id=command.notebook_id,
                    type=source_type.value,
                    origin=origin,
                    display_title=command.display_title,
                    availability=Availability.ACTIVE.value,
                    created_by_user_id=command.actor_id,
                )
            )
            connection.execute(
                sa.insert(source_versions).values(
                    id=version_id,
                    source_id=source_id,
                    version_number=1,
                    original_blob_id=blob.id,
                    content_sha256=blob.content_sha256,
                    content_size_bytes=blob.size_bytes,
                    status="activating",
                    created_by_user_id=command.actor_id,
                )
            )
            connection.execute(
                pg_insert(blob_references)
                .values(
                    blob_id=blob.id,
                    referrer_kind="source_version",
                    referrer_id=version_id,
                )
                .on_conflict_do_nothing()
            )
            row = connection.execute(
                self._select_view().where(sources.c.id == source_id)
            ).mappings().one()
        return self._view(row), True

    def _acquire_refresh(
        self, command: AcquireSourceCommand, blob: BlobObject
    ) -> tuple[SourceView, bool]:
        source_id = command.refresh_source_id
        if source_id is None:
            raise SourceNotFoundError
        with self._engine.begin() as connection:
            source = connection.execute(
                sa.select(sources.c.id)
                .join(
                    notebook_memberships,
                    notebook_memberships.c.notebook_id == sources.c.notebook_id,
                )
                .where(
                    sources.c.id == source_id,
                    sources.c.notebook_id == command.notebook_id,
                    sources.c.type == SourceType.WEB_URL.value,
                    sources.c.availability != Availability.DELETED_TOMBSTONED.value,
                    notebook_memberships.c.user_id == command.actor_id,
                )
                .with_for_update(of=sources)
            ).first()
            if source is None:
                raise SourceNotFoundError
            latest = connection.execute(
                sa.select(source_versions)
                .where(source_versions.c.source_id == source_id)
                .order_by(source_versions.c.version_number.desc())
                .limit(1)
            ).mappings().one()
            version_id = uuid.uuid4()
            connection.execute(
                sa.insert(source_versions).values(
                    id=version_id,
                    source_id=source_id,
                    version_number=int(latest["version_number"]) + 1,
                    original_blob_id=blob.id,
                    content_sha256=blob.content_sha256,
                    content_size_bytes=blob.size_bytes,
                    status="activating",
                    created_by_user_id=command.actor_id,
                )
            )
            connection.execute(
                pg_insert(blob_references)
                .values(blob_id=blob.id, referrer_kind="source_version", referrer_id=version_id)
                .on_conflict_do_nothing()
            )
            row = connection.execute(
                self._select_view().where(sources.c.id == source_id)
            ).mappings().one()
        return self._view(row), True

    def mark_refresh_failed(self, source_id: uuid.UUID, actor_id: uuid.UUID) -> None:
        """Mark a refresh failure without replacing the active source version."""
        with self._engine.begin() as connection:
            connection.execute(
                sa.update(sources)
                .where(
                    sources.c.id == source_id,
                    sa.exists().where(
                        notebook_memberships.c.notebook_id == sources.c.notebook_id,
                        notebook_memberships.c.user_id == actor_id,
                    ),
                )
                .values(availability=Availability.STALE.value, updated_at=sa.func.now())
            )

    def refresh_url(self, source_id: uuid.UUID, actor_id: uuid.UUID) -> str | None:
        """Return the stable URL identity for a visible web source."""
        with self._engine.begin() as connection:
            origin = connection.scalar(
                sa.select(sources.c.origin)
                .join(
                    notebook_memberships,
                    notebook_memberships.c.notebook_id == sources.c.notebook_id,
                )
                .where(
                    sources.c.id == source_id,
                    sources.c.type == SourceType.WEB_URL.value,
                    notebook_memberships.c.user_id == actor_id,
                )
            )
        if origin is None or not str(origin).startswith("web_url:"):
            return None
        remote = str(origin).removeprefix("web_url:")
        return remote.rsplit(":captured:", maxsplit=1)[0]

    def acquire_unavailable(
        self,
        command: AcquireSourceCommand,
        *,
        origin: str,
        source_type: SourceType,
        reason: str,
    ) -> tuple[SourceView, bool]:
        """Persist a blob-less source version in an explicit unavailable state."""
        import hashlib  # noqa: PLC0415 - content identity for the URL-only version

        with self._engine.begin() as connection:
            connection.execute(
                sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"),
                {"identity": f"{command.notebook_id}:{origin}"},
            )
            existing = connection.execute(
                self._select_view().where(
                    sources.c.notebook_id == command.notebook_id,
                    sources.c.origin == origin,
                )
            ).mappings().first()
            if existing is not None:
                return self._view(existing), False
            source_id = uuid.uuid4()
            version_id = uuid.uuid4()
            connection.execute(
                sa.insert(sources).values(
                    id=source_id,
                    notebook_id=command.notebook_id,
                    type=source_type.value,
                    origin=origin,
                    display_title=command.display_title,
                    availability=Availability.ACTIVE.value,
                    created_by_user_id=command.actor_id,
                )
            )
            connection.execute(
                sa.insert(source_versions).values(
                    id=version_id,
                    source_id=source_id,
                    version_number=1,
                    original_blob_id=None,
                    content_sha256=hashlib.sha256(origin.encode("utf-8")).hexdigest(),
                    content_size_bytes=None,
                    status="parse_failed",
                    parse_error_code=reason,
                    created_by_user_id=command.actor_id,
                )
            )
            row = connection.execute(
                self._select_view().where(sources.c.id == source_id)
            ).mappings().one()
        return self._view(row), True

    def get(self, source_id: uuid.UUID, actor_id: uuid.UUID) -> SourceView | None:
        """Return one source only through an actor notebook membership."""
        with self._engine.begin() as connection:
            row = connection.execute(
                self._select_view()
                .join(
                    notebook_memberships,
                    notebook_memberships.c.notebook_id == sources.c.notebook_id,
                )
                .where(
                    sources.c.id == source_id,
                    notebook_memberships.c.user_id == actor_id,
                )
            ).mappings().first()
        return None if row is None else self._view(row)

    def list(self, notebook_id: uuid.UUID, actor_id: uuid.UUID) -> list[SourceView]:
        """List each notebook source at its newest persisted version."""
        with self._engine.begin() as connection:
            rows = connection.execute(
                sa.select(
                    sources.c.id.label("source_id"),
                    sources.c.notebook_id,
                    sources.c.type,
                    sources.c.display_title,
                    sources.c.availability,
                    sources.c.etag,
                    source_versions.c.id.label("source_version_id"),
                    source_versions.c.content_sha256,
                    source_versions.c.content_size_bytes,
                    source_versions.c.status.label("version_status"),
                    source_versions.c.original_blob_id,
                    _CANONICAL_ROOT_NODE_ID.label("canonical_root_node_id"),
                )
                .join(source_versions, source_versions.c.source_id == sources.c.id)
                .join(
                    notebook_memberships,
                    notebook_memberships.c.notebook_id == sources.c.notebook_id,
                )
                .where(
                    sources.c.notebook_id == notebook_id,
                    notebook_memberships.c.user_id == actor_id,
                )
                .order_by(sources.c.updated_at.desc(), source_versions.c.version_number.desc())
            ).mappings()
            latest: list[SourceView] = []
            seen: set[uuid.UUID] = set()
            for row in rows:
                source_id = row["source_id"]
                if source_id in seen:
                    continue
                seen.add(source_id)
                latest.append(self._view(row))
        return latest

    def rename(
        self, source_id: uuid.UUID, actor_id: uuid.UUID, title: str, etag: str
    ) -> SourceView:
        """CAS-update title metadata through an actor notebook membership."""
        with self._engine.begin() as connection:
            result = connection.execute(
                sa.update(sources)
                .where(
                    sources.c.id == source_id,
                    sources.c.etag == etag,
                    sources.c.notebook_id.in_(
                        sa.select(notebook_memberships.c.notebook_id).where(
                            notebook_memberships.c.user_id == actor_id
                        )
                    ),
                )
                .values(
                    display_title=title,
                    revision=sources.c.revision + 1,
                    etag=sa.cast(sources.c.revision + 1, sa.Text),
                    updated_at=sa.func.now(),
                )
            )
            if result.rowcount == 0:
                visible = connection.execute(
                    sa.select(sources.c.id).where(
                        sources.c.id == source_id,
                        sources.c.notebook_id.in_(
                            sa.select(notebook_memberships.c.notebook_id).where(
                                notebook_memberships.c.user_id == actor_id
                            )
                        ),
                    )
                ).first()
                if visible is None:
                    raise SourceNotFoundError
                raise SourceConflictError
            row = connection.execute(
                self._select_view().where(sources.c.id == source_id)
            ).mappings().one()
        return self._view(row)

    def set_selected(
        self, source_id: uuid.UUID, actor_id: uuid.UUID, *, selected: bool
    ) -> SourceView:
        """Toggle active/removal state without deleting retained bytes."""
        availability = (
            Availability.ACTIVE if selected else Availability.DELETED_TOMBSTONED
        )
        with self._engine.begin() as connection:
            result = connection.execute(
                sa.update(sources)
                .where(
                    sources.c.id == source_id,
                    sources.c.notebook_id.in_(
                        sa.select(notebook_memberships.c.notebook_id).where(
                            notebook_memberships.c.user_id == actor_id
                        )
                    ),
                )
                .values(
                    availability=availability.value,
                    revision=sources.c.revision + 1,
                    etag=sa.cast(sources.c.revision + 1, sa.Text),
                    updated_at=sa.func.now(),
                )
            )
            if result.rowcount == 0:
                raise SourceNotFoundError
            row = connection.execute(
                self._select_view().where(sources.c.id == source_id)
            ).mappings().one()
        return self._view(row)

    def activate(self, source_id: uuid.UUID, actor_id: uuid.UUID) -> bool:
        """Atomically promote one parsed version with its canonical document."""
        return self._activation.activate(source_id, actor_id)

    def active_document_id(self, source_id: uuid.UUID, actor_id: uuid.UUID) -> uuid.UUID | None:
        """Return the active canonical document id of an activated source (or None)."""
        with self._engine.begin() as connection:
            row = connection.execute(
                sa.select(canonical_documents.c.id)
                .join(
                    source_versions,
                    source_versions.c.id
                    == canonical_documents.c.source_version_id,
                )
                .where(
                    source_versions.c.source_id == source_id,
                    canonical_documents.c.active.is_(True),
                )
            ).first()
        return None if row is None else row[0]

    def guide(self, source_id: uuid.UUID, actor_id: uuid.UUID) -> SourceGuideView | None:
        """Return the phase-one deterministic Source Guide for an active source."""
        return self._guide.guide(source_id, actor_id)

    def effective_restrictions(
        self, source_id: uuid.UUID, actor_id: uuid.UUID
    ) -> EffectiveRestrictions:
        """Effective deny/reuse/export state across content-bearing ancestors."""
        return self._guide.effective_restrictions(source_id, actor_id)

    @staticmethod
    def _origin(command: AcquireSourceCommand, blob: BlobObject) -> str:
        if command.web_capture is not None:
            return f"web_url:{command.web_capture.requested_url}"
        return f"{command.origin_kind}:{IMPORTER_VERSION}:sha256:{blob.content_sha256}"

    @staticmethod
    def _source_type(blob: BlobObject) -> SourceType:
        try:
            return _SOURCE_TYPES[blob.content_type or ""]
        except KeyError as exc:
            raise AssertionError(
                f"unsupported identified content type: {blob.content_type}"
            ) from exc

    @staticmethod
    def _select_view() -> sa.Select[
        tuple[
            uuid.UUID,
            uuid.UUID,
            str,
            str,
            str,
            str,
            uuid.UUID,
            str,
            int,
            str,
            uuid.UUID,
            uuid.UUID | None,
        ]
    ]:
        return (
            sa.select(
                sources.c.id.label("source_id"),
                sources.c.notebook_id,
                sources.c.type,
                sources.c.display_title,
                sources.c.availability,
                sources.c.etag,
                source_versions.c.id.label("source_version_id"),
                source_versions.c.content_sha256,
                source_versions.c.content_size_bytes,
                source_versions.c.status.label("version_status"),
                source_versions.c.original_blob_id,
                _CANONICAL_ROOT_NODE_ID.label("canonical_root_node_id"),
            )
            .join(source_versions, source_versions.c.source_id == sources.c.id)
            .order_by(source_versions.c.version_number.desc())
            .limit(1)
        )

    @staticmethod
    def _view(row: RowMapping) -> SourceView:
        return SourceView(
            source_id=row["source_id"],
            source_version_id=row["source_version_id"],
            notebook_id=row["notebook_id"],
            source_type=SourceType(row["type"]),
            display_title=row["display_title"],
            availability=Availability(row["availability"]),
            content_sha256=row["content_sha256"],
            content_size_bytes=row["content_size_bytes"],
            version_status=row["version_status"],
            etag=row["etag"],
            blob_id=row["original_blob_id"],
            canonical_root_node_id=row["canonical_root_node_id"],
        )
