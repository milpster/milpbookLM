"""PostgreSQL adapter for logical notes and insert-only note revisions."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from milpbooklm_application.note_core import (
    NoteConflictError,
    NoteNotEditableError,
    NoteRevisionView,
    NoteSnapshot,
    NoteView,
    SavedResponseView,
)
from milpbooklm_domain.notes import ContentKind, ContentRef, NoteKind
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import RowMapping

from .db.tables.conversation import conversations, messages
from .db.tables.sources import provenance_edges
from .db.tables.studio import note_revisions, notes


class PgNoteStore:
    """Persist notes while exposing no revision update or delete operation."""

    def __init__(self, engine: sa.engine.Engine) -> None:
        """Bind the application-role database engine."""
        self._engine: sa.engine.Engine
        self._engine = engine

    def create(self, snapshot: NoteSnapshot) -> NoteSnapshot:
        """Insert a note and its first revision atomically."""
        note = snapshot.note
        revision = snapshot.revision
        with self._engine.begin() as connection:
            _ = connection.execute(
                sa.insert(notes).values(
                    id=note.note_id,
                    notebook_id=note.notebook_id,
                    kind=note.kind.value,
                    editable=note.editable,
                    title=note.title,
                    created_by_user_id=note.created_by_user_id,
                )
            )
            self._insert_revision(connection, revision)
            row = connection.execute(
                sa.update(notes)
                .where(notes.c.id == note.note_id)
                .values(
                    current_revision_id=revision.revision_id,
                    revision=1,
                    etag="1",
                )
                .returning(notes)
            ).mappings().one()
        return NoteSnapshot(_note_view(row), revision)

    def get_note(self, note_id: uuid.UUID) -> NoteView | None:
        """Load logical note metadata without changing its current revision."""
        with self._engine.begin() as connection:
            row = connection.execute(
                sa.select(notes).where(notes.c.id == note_id)
            ).mappings().one_or_none()
        return _note_view(row) if row is not None else None

    def list_notes(self, notebook_id: uuid.UUID) -> list[NoteView]:
        """List notebook notes in stable creation order."""
        with self._engine.begin() as connection:
            rows = connection.execute(
                sa.select(notes)
                .where(notes.c.notebook_id == notebook_id)
                .order_by(notes.c.created_at, notes.c.id)
            ).mappings().all()
        return [_note_view(row) for row in rows]

    def get_revision(self, revision_id: uuid.UUID) -> NoteRevisionView | None:
        """Load one exact immutable revision by id."""
        with self._engine.begin() as connection:
            row = connection.execute(
                sa.select(note_revisions).where(note_revisions.c.id == revision_id)
            ).mappings().one_or_none()
        return _revision_view(row) if row is not None else None

    def list_revisions(self, note_id: uuid.UUID) -> list[NoteRevisionView]:
        """List every retained revision in publication order."""
        with self._engine.begin() as connection:
            rows = connection.execute(
                sa.select(note_revisions)
                .where(note_revisions.c.note_id == note_id)
                .order_by(note_revisions.c.revision_number)
            ).mappings().all()
        return [_revision_view(row) for row in rows]

    def append_revision(
        self, note_id: uuid.UUID, expected_etag: str, revision: NoteRevisionView
    ) -> NoteSnapshot | None:
        """Serialize collaborators and append only when the submitted ETag is current."""
        with self._engine.begin() as connection:
            current = connection.execute(
                sa.select(notes).where(notes.c.id == note_id).with_for_update()
            ).mappings().one_or_none()
            if current is None:
                return None
            if not current["editable"]:
                raise NoteNotEditableError(note_id)
            if current["etag"] != expected_etag:
                raise NoteConflictError(note_id)
            next_number = int(current["revision"]) + 1
            persisted = NoteRevisionView(
                revision.revision_id,
                revision.note_id,
                next_number,
                revision.content,
                revision.content_sha256,
                revision.author_user_id,
                revision.provenance_refs,
                revision.content_dependencies,
                revision.created_at,
            )
            self._insert_revision(connection, persisted)
            updated = connection.execute(
                sa.update(notes)
                .where(notes.c.id == note_id, notes.c.etag == expected_etag)
                .values(
                    current_revision_id=persisted.revision_id,
                    revision=next_number,
                    etag=str(next_number),
                )
                .returning(notes)
            ).mappings().one()
        return NoteSnapshot(_note_view(updated), persisted)

    def revisions_for_notebook(
        self, notebook_id: uuid.UUID, revision_ids: tuple[uuid.UUID, ...]
    ) -> tuple[NoteRevisionView, ...]:
        """Resolve exact revisions only when every row belongs to the named notebook."""
        if not revision_ids:
            return ()
        with self._engine.begin() as connection:
            rows = connection.execute(
                sa.select(note_revisions)
                .join(notes, notes.c.id == note_revisions.c.note_id)
                .where(
                    notes.c.notebook_id == notebook_id,
                    note_revisions.c.id.in_(revision_ids),
                )
            ).mappings().all()
        by_id = {row["id"]: _revision_view(row) for row in rows}
        return tuple(by_id[revision_id] for revision_id in revision_ids if revision_id in by_id)

    def saved_response(
        self, actor_id: uuid.UUID, notebook_id: uuid.UUID, message_id: uuid.UUID
    ) -> SavedResponseView | None:
        """Resolve only an assistant response from the actor's private conversation."""
        with self._engine.begin() as connection:
            row = connection.execute(
                sa.select(messages.c.id, messages.c.content, messages.c.manifest_id)
                .join(conversations, conversations.c.id == messages.c.conversation_id)
                .where(
                    messages.c.id == message_id,
                    messages.c.role == "assistant",
                    messages.c.tombstone_at.is_(None),
                    conversations.c.owner_user_id == actor_id,
                    conversations.c.notebook_id == notebook_id,
                    conversations.c.visibility == "private",
                )
            ).one_or_none()
        if row is None:
            return None
        return SavedResponseView(row.id, row.content, row.manifest_id)

    def record_promotion(
        self, note_revision_id: uuid.UUID, source_version_id: uuid.UUID
    ) -> None:
        """Record the note-revision origin of an ingestion-created source version."""
        with self._engine.begin() as connection:
            _ = connection.execute(
                pg_insert(provenance_edges)
                .values(
                    id=uuid.uuid4(),
                    from_type="source_version",
                    from_id=source_version_id,
                    edge_type="derived_from",
                    to_type="note_revision",
                    to_id=note_revision_id,
                    transform_identity="note_to_source",
                    transform_version="1",
                    confidence=1.0,
                )
                .on_conflict_do_nothing()
            )

    @staticmethod
    def _insert_revision(
        connection: sa.engine.Connection, revision: NoteRevisionView
    ) -> None:
        _ = connection.execute(
            sa.insert(note_revisions).values(
                id=revision.revision_id,
                note_id=revision.note_id,
                revision_number=revision.revision_number,
                content=revision.content,
                content_sha256=revision.content_sha256,
                author_user_id=revision.author_user_id,
                provenance_refs=_refs_payload(revision.provenance_refs),
                content_dependencies=_refs_payload(revision.content_dependencies),
            )
        )


def _note_view(row: RowMapping) -> NoteView:
    return NoteView(
        row["id"],
        row["notebook_id"],
        NoteKind(row["kind"]),
        bool(row["editable"]),
        row["title"],
        row["current_revision_id"],
        row["created_by_user_id"],
        int(row["revision"]),
        row["etag"],
        row["created_at"],
        row["updated_at"],
    )


def _revision_view(row: RowMapping) -> NoteRevisionView:
    return NoteRevisionView(
        row["id"],
        row["note_id"],
        int(row["revision_number"]),
        row["content"],
        row["content_sha256"],
        row["author_user_id"],
        _refs(row["provenance_refs"]),
        _refs(row["content_dependencies"]),
        row["created_at"],
    )


def _refs(raw: list[dict[str, str]] | None) -> tuple[ContentRef, ...]:
    return tuple(ContentRef(ContentKind(item["kind"]), uuid.UUID(item["id"])) for item in raw or ())


def _refs_payload(refs: tuple[ContentRef, ...]) -> list[dict[str, str]]:
    return [{"kind": ref.kind.value, "id": str(ref.id)} for ref in refs]
