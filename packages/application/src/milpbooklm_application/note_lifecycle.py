"""Note creation, immutable edits, transforms, saved responses, and promotion."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime

from milpbooklm_domain.notes import ContentKind, ContentRef, NoteKind, revision_content_sha256

from .note_core import (
    CreateNoteCommand,
    EditNoteCommand,
    NoteNotEditableError,
    NotePromotionView,
    NoteRevisionView,
    NoteSelectionError,
    NoteSnapshot,
    NoteStore,
    NoteTransformProvider,
    NoteView,
    PromoteNoteCommand,
    SaveResponseToNoteCommand,
    SourceIngestion,
    TransformNotesCommand,
    note_content_text,
)
from .source_acquisition import AcquireSourceCommand


@dataclass(frozen=True, slots=True)
class _NewNote:
    actor_id: uuid.UUID
    notebook_id: uuid.UUID
    title: str
    kind: NoteKind
    editable: bool
    content: dict[str, object]
    provenance_refs: tuple[ContentRef, ...] = ()
    content_dependencies: tuple[ContentRef, ...] = ()


class CreateNote:
    """Create a user note with revision one as one persistence operation."""

    def __init__(self, store: NoteStore) -> None:
        """Bind immutable note persistence."""
        self._store: NoteStore
        self._store = store

    def __call__(self, command: CreateNoteCommand) -> NoteSnapshot:
        """Create the requested user note."""
        return self._store.create(
            _new_snapshot(
                _NewNote(
                    command.actor_id,
                    command.notebook_id,
                    command.title,
                    NoteKind.USER,
                    True,
                    command.content,
                )
            )
        )


class EditNote:
    """Append a revision without mutating any previously published content."""

    def __init__(self, store: NoteStore) -> None:
        """Bind immutable note persistence."""
        self._store: NoteStore
        self._store = store

    def __call__(self, command: EditNoteCommand) -> NoteSnapshot | None:
        """Append content when the logical note exists and remains editable."""
        note = self._store.get_note(command.note_id)
        if note is None:
            return None
        if not note.editable:
            raise NoteNotEditableError(note.note_id)
        revision = _revision(
            note_id=note.note_id,
            revision_number=note.revision + 1,
            actor_id=command.actor_id,
            content=command.content,
        )
        return self._store.append_revision(note.note_id, command.expected_etag, revision)


class SaveResponseToNote:
    """Create a non-editable note from an explicitly named private response."""

    def __init__(self, store: NoteStore) -> None:
        """Bind immutable note persistence."""
        self._store: NoteStore
        self._store = store

    def __call__(self, command: SaveResponseToNoteCommand) -> NoteSnapshot | None:
        """Save an actor-owned assistant response when it exists."""
        response = self._store.saved_response(
            command.actor_id, command.notebook_id, command.message_id
        )
        if response is None:
            return None
        message_ref = ContentRef(ContentKind.MESSAGE, response.message_id)
        return self._store.create(
            _new_snapshot(
                _NewNote(
                    command.actor_id,
                    command.notebook_id,
                    command.title,
                    NoteKind.SAVED_CHAT_RESPONSE,
                    False,
                    {"blocks": [{"type": "paragraph", "text": response.content}]},
                    (message_ref,),
                    (message_ref,),
                )
            )
        )


class TransformNotes:
    """Generate a new note from exact, authorization-scoped input revisions."""

    def __init__(self, store: NoteStore, provider: NoteTransformProvider) -> None:
        """Bind note persistence and the configured transform provider."""
        self._store: NoteStore
        self._provider: NoteTransformProvider
        self._store = store
        self._provider = provider

    def __call__(self, command: TransformNotesCommand) -> NoteSnapshot:
        """Transform only exact selected revisions into a new note."""
        if not command.revision_ids or len(set(command.revision_ids)) != len(
            command.revision_ids
        ):
            raise NoteSelectionError(command.revision_ids)
        revisions = self._store.revisions_for_notebook(command.notebook_id, command.revision_ids)
        if len(revisions) != len(command.revision_ids):
            raise NoteSelectionError(command.revision_ids)
        content = self._provider.transform(command.kind, revisions)
        refs = tuple(
            ContentRef(ContentKind.NOTE_REVISION, revision.revision_id)
            for revision in revisions
        )
        return self._store.create(
            _new_snapshot(
                _NewNote(
                    command.actor_id,
                    command.notebook_id,
                    command.title,
                    NoteKind.USER,
                    True,
                    content,
                    refs,
                    refs,
                )
            )
        )


class PromoteNoteToSource:
    """Feed one revision into existing acquisition and persist its provenance edge."""

    def __init__(self, store: NoteStore, ingestion: SourceIngestion) -> None:
        """Bind note persistence to the existing source-ingestion pipeline."""
        self._store: NoteStore
        self._ingestion: SourceIngestion
        self._store = store
        self._ingestion = ingestion

    async def __call__(self, command: PromoteNoteCommand) -> NotePromotionView:
        """Promote one exact revision and retain its provenance edge."""
        revisions = self._store.revisions_for_notebook(
            command.notebook_id, (command.revision_id,)
        )
        if not revisions:
            raise NoteSelectionError((command.revision_id,))
        revision = revisions[0]
        source, created, job_id = await self._ingestion(
            AcquireSourceCommand(
                notebook_id=command.notebook_id,
                actor_id=command.actor_id,
                display_title=command.title,
                origin_kind=f"note_revision:{revision.revision_id}",
            ),
            _one_shot(note_content_text(revision.content).encode()),
        )
        self._store.record_promotion(revision.revision_id, source.source_version_id)
        return NotePromotionView(source.source_id, source.source_version_id, job_id, created)


def _new_snapshot(command: _NewNote) -> NoteSnapshot:
    now = datetime.now(tz=UTC)
    note_id = uuid.uuid4()
    revision = _revision(
        note_id=note_id,
        revision_number=1,
        actor_id=command.actor_id,
        content=command.content,
        provenance_refs=command.provenance_refs,
        content_dependencies=command.content_dependencies,
        created_at=now,
    )
    note = NoteView(
        note_id,
        command.notebook_id,
        command.kind,
        command.editable,
        command.title,
        revision.revision_id,
        command.actor_id,
        1,
        "1",
        now,
        now,
    )
    return NoteSnapshot(note, revision)


def _revision(
    *,
    note_id: uuid.UUID,
    revision_number: int,
    actor_id: uuid.UUID,
    content: dict[str, object],
    provenance_refs: tuple[ContentRef, ...] = (),
    content_dependencies: tuple[ContentRef, ...] = (),
    created_at: datetime | None = None,
) -> NoteRevisionView:
    return NoteRevisionView(
        uuid.uuid4(),
        note_id,
        revision_number,
        content,
        revision_content_sha256(content),
        actor_id,
        provenance_refs,
        content_dependencies,
        created_at or datetime.now(tz=UTC),
    )


async def _one_shot(data: bytes) -> AsyncIterator[bytes]:
    yield data
