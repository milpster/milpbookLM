"""PostgreSQL note persistence, immutable revisions, transforms, and promotion."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
from milpbooklm_adapters.db.connections import make_engine
from milpbooklm_adapters.grounding import PgGroundingStore
from milpbooklm_adapters.grounding_completion import FakeGroundingCompletionProvider
from milpbooklm_adapters.note_store import PgNoteStore
from milpbooklm_application.grounding import (
    GenerateGroundedAnswer,
    GroundingError,
    GroundingRequest,
)
from milpbooklm_application.note_core import (
    CreateNoteCommand,
    EditNoteCommand,
    NoteConflictError,
    NoteNotEditableError,
    NoteRevisionView,
    NoteSelectionError,
    NoteTransformKind,
    PromoteNoteCommand,
    SaveResponseToNoteCommand,
    TransformNotesCommand,
)
from milpbooklm_application.note_lifecycle import (
    CreateNote,
    EditNote,
    PromoteNoteToSource,
    SaveResponseToNote,
    TransformNotes,
)
from milpbooklm_application.retrieval import RetrieveChunks
from milpbooklm_application.source_acquisition import AcquireSourceCommand, SourceView
from milpbooklm_domain.notes import ContentKind, NoteKind
from milpbooklm_domain.sources import Availability, SourceType

from tests.domain.invariants._factories import Db


def _scratch_dsn() -> str | None:
    socket_dir = Path("scratch/t13-smoke")
    if not (socket_dir / ".s.PGSQL.29521").exists():
        return None
    return (
        "postgresql://milpbooklm_app:milpbooklm_app@/milpbooklm_t13"
        f"?host={socket_dir.resolve()}&port=29521"
    )


@pytest.fixture(name="pg")
def _pg() -> Db:
    dsn = _scratch_dsn()
    if dsn is None:
        pytest.skip("live PostgreSQL acceptance stack is not running")
    return Db(dsn)


def _store() -> PgNoteStore:
    dsn = _scratch_dsn()
    assert dsn is not None
    return PgNoteStore(make_engine(dsn.replace("postgresql://", "postgresql+psycopg://")))


def _content(text: str) -> dict[str, object]:
    return {"blocks": [{"type": "paragraph", "text": text}]}


@dataclass(slots=True)
class RecordingTransformer:
    """Deterministic transform fake that records the exact pinned inputs."""

    seen: tuple[uuid.UUID, ...] = ()

    def transform(
        self, kind: NoteTransformKind, revisions: tuple[NoteRevisionView, ...]
    ) -> dict[str, object]:
        self.seen = tuple(revision.revision_id for revision in revisions)
        joined = " | ".join(str(revision.content) for revision in revisions)
        return _content(f"{kind.value}: {joined}")


@dataclass(slots=True)
class RecordingIngestion:
    """Source-ingestion fake that consumes the real note byte stream."""

    source: SourceView
    payload: bytes = b""
    origin_kind: str = ""

    async def __call__(
        self, command: AcquireSourceCommand, chunks: AsyncIterable[bytes]
    ) -> tuple[SourceView, bool, uuid.UUID]:
        collected = bytearray()
        async for chunk in chunks:
            collected.extend(chunk)
        self.payload = bytes(collected)
        self.origin_kind = command.origin_kind
        return self.source, True, uuid.uuid4()


def test_edit_creates_new_revision_and_preserves_prior_content(pg: Db) -> None:
    # Given
    actor = pg.user()
    notebook = pg.notebook(actor)
    store = _store()
    created = CreateNote(store)(
        CreateNoteCommand(actor, notebook, "Draft", _content("version one"))
    )

    # When
    edited = EditNote(store)(
        EditNoteCommand(actor, created.note.note_id, created.note.etag, _content("version two"))
    )

    # Then
    assert edited is not None
    assert edited.revision.revision_number == created.revision.revision_number + 1
    assert edited.revision.content == _content("version two")
    retained = store.get_revision(created.revision.revision_id)
    assert retained is not None
    assert retained.content == _content("version one")
    revision_numbers = [
        revision.revision_number
        for revision in store.list_revisions(created.note.note_id)
    ]
    assert revision_numbers == [1, 2]


def test_identical_current_content_is_an_idempotent_revision_save(pg: Db) -> None:
    # Given
    actor = pg.user()
    notebook = pg.notebook(actor)
    store = _store()
    created = CreateNote(store)(
        CreateNoteCommand(actor, notebook, "Draft", _content("unchanged"))
    )

    # When
    saved = EditNote(store)(
        EditNoteCommand(actor, created.note.note_id, created.note.etag, _content("unchanged"))
    )

    # Then
    assert saved is not None
    assert saved.note.etag == created.note.etag
    assert saved.revision.revision_id == created.revision.revision_id
    revision_numbers = [
        revision.revision_number for revision in store.list_revisions(created.note.note_id)
    ]
    assert revision_numbers == [1]


def test_stale_identical_content_remains_a_conflict(pg: Db) -> None:
    # Given
    actor = pg.user()
    notebook = pg.notebook(actor)
    store = _store()
    created = CreateNote(store)(CreateNoteCommand(actor, notebook, "Draft", _content("one")))
    updated = EditNote(store)(
        EditNoteCommand(actor, created.note.note_id, created.note.etag, _content("two"))
    )
    assert updated is not None

    # When / Then
    with pytest.raises(NoteConflictError):
        _ = EditNote(store)(
            EditNoteCommand(actor, created.note.note_id, created.note.etag, _content("two"))
        )


def test_saved_response_is_actor_owned_and_non_editable(pg: Db) -> None:
    # Given
    actor = pg.user()
    other_actor = pg.user()
    notebook = pg.notebook(actor)
    manifest = pg.manifest(notebook_id=notebook, created_by=actor, op_kind="ordinary_chat")
    conversation = pg.conversation(actor, notebook_id=notebook)
    message = pg.message(
        conversation,
        manifest,
        role="assistant",
        content="Saved private response",
    )
    store = _store()

    # When
    saved = SaveResponseToNote(store)(
        SaveResponseToNoteCommand(actor, notebook, message, "Saved answer")
    )

    # Then
    assert saved is not None
    assert saved.note.kind is NoteKind.SAVED_CHAT_RESPONSE
    assert not saved.note.editable
    assert saved.revision.content_dependencies[0].kind is ContentKind.MESSAGE
    assert saved.revision.content_dependencies[0].id == message
    assert (
        SaveResponseToNote(store)(
            SaveResponseToNoteCommand(other_actor, notebook, message, "Leak attempt")
        )
        is None
    )
    with pytest.raises(NoteNotEditableError):
        EditNote(store)(
            EditNoteCommand(
                actor,
                saved.note.note_id,
                saved.note.etag,
                _content("mutated response"),
            )
        )


def test_stale_etag_conflict_survives_transaction_exit(pg: Db) -> None:
    # Given
    actor = pg.user()
    notebook = pg.notebook(actor)
    store = _store()
    created = CreateNote(store)(
        CreateNoteCommand(actor, notebook, "Draft", _content("version one"))
    )
    edited = EditNote(store)(
        EditNoteCommand(actor, created.note.note_id, created.note.etag, _content("two"))
    )
    assert edited is not None

    # When / Then: the conflict is raised INSIDE engine.begin(); the typed
    # error must survive the context-manager unwind (the frozen-dataclass
    # __traceback__ assignment used to replace it with TypeError -> 500).
    with pytest.raises(NoteConflictError, match="changed before the edit was applied"):
        EditNote(store)(
            EditNoteCommand(
                actor,
                created.note.note_id,
                created.note.etag,  # superseded by the edit above
                _content("stale write"),
            )
        )


def test_non_editable_append_survives_transaction_exit(pg: Db) -> None:
    # Given
    actor = pg.user()
    notebook = pg.notebook(actor)
    manifest = pg.manifest(notebook_id=notebook, created_by=actor, op_kind="ordinary_chat")
    conversation = pg.conversation(actor, notebook_id=notebook)
    message = pg.message(
        conversation, manifest, role="assistant", content="Saved private response"
    )
    store = _store()
    saved = SaveResponseToNote(store)(
        SaveResponseToNoteCommand(actor, notebook, message, "Saved answer")
    )
    assert saved is not None
    revision = NoteRevisionView(
        revision_id=uuid.uuid4(),
        note_id=saved.note.note_id,
        revision_number=saved.note.revision + 1,
        content=_content("attempt"),
        content_sha256="0" * 64,
        author_user_id=actor,
        provenance_refs=(),
        content_dependencies=(),
        created_at=datetime.now(UTC),
    )

    # When / Then: store-level append bypasses the lifecycle editability
    # guard, so the raise happens inside the row-lock transaction.
    with pytest.raises(NoteNotEditableError, match="is not editable"):
        store.append_revision(saved.note.note_id, saved.note.etag, revision)


def test_transform_pins_only_explicit_revisions(pg: Db) -> None:
    # Given
    actor = pg.user()
    notebook = pg.notebook(actor)
    store = _store()
    first = CreateNote(store)(CreateNoteCommand(actor, notebook, "One", _content("one")))
    second = CreateNote(store)(CreateNoteCommand(actor, notebook, "Two", _content("two")))
    unselected = CreateNote(store)(CreateNoteCommand(actor, notebook, "Three", _content("secret")))
    transformer = RecordingTransformer()

    # When
    transformed = TransformNotes(store, transformer)(
        TransformNotesCommand(
            actor,
            notebook,
            (first.revision.revision_id, second.revision.revision_id),
            NoteTransformKind.COMBINE,
            "Combined",
        )
    )

    # Then
    assert transformer.seen == (first.revision.revision_id, second.revision.revision_id)
    assert unselected.revision.revision_id not in transformer.seen
    assert tuple(ref.id for ref in transformed.revision.content_dependencies) == transformer.seen


def test_transform_rejects_duplicate_revision_selection(pg: Db) -> None:
    # Given
    actor = pg.user()
    notebook = pg.notebook(actor)
    store = _store()
    selected = CreateNote(store)(
        CreateNoteCommand(actor, notebook, "Selected", _content("one"))
    )
    revision_id = selected.revision.revision_id

    # When / Then
    with pytest.raises(NoteSelectionError):
        _ = TransformNotes(store, RecordingTransformer())(
            TransformNotesCommand(
                actor,
                notebook,
                (revision_id, revision_id),
                NoteTransformKind.COMBINE,
                "Duplicate",
            )
        )


@pytest.mark.anyio
async def test_promotion_uses_ingestion_and_records_revision_provenance(pg: Db) -> None:
    # Given
    actor = pg.user()
    notebook = pg.notebook(actor)
    source_id = pg.source(notebook, actor)
    source_version_id = pg.source_version(source_id, actor)
    store = _store()
    note = CreateNote(store)(CreateNoteCommand(actor, notebook, "Promote", _content("alpha")))
    ingestion = RecordingIngestion(
        SourceView(
            source_id,
            source_version_id,
            notebook,
            SourceType.PLAIN_TEXT,
            "Promote",
            Availability.ACTIVE,
            "a" * 64,
            5,
            "activating",
            "0",
            uuid.uuid4(),
        )
    )

    # When
    promoted = await PromoteNoteToSource(store, ingestion)(
        PromoteNoteCommand(actor, notebook, note.revision.revision_id, "Promoted note")
    )

    # Then
    assert promoted.source_version_id == source_version_id
    assert b"alpha" in ingestion.payload
    assert str(note.revision.revision_id) in ingestion.origin_kind
    edge = pg.conn.execute(
        "SELECT edge_type, from_id, to_id, transform_identity "
        "FROM provenance_edges WHERE from_id = %s AND to_id = %s",
        (source_version_id, note.revision.revision_id),
    ).fetchone()
    assert edge == ("derived_from", source_version_id, note.revision.revision_id, "note_to_source")


def test_chat_freeze_resolves_only_explicit_authorized_revision(pg: Db) -> None:
    # Given
    actor = pg.user()
    outsider = pg.user()
    notebook = pg.notebook(actor)
    store = _store()
    selected = CreateNote(store)(
        CreateNoteCommand(actor, notebook, "Selected", _content("visible"))
    )
    _ = EditNote(store)(
        EditNoteCommand(
            actor,
            selected.note.note_id,
            selected.note.etag,
            _content("new revision"),
        )
    )
    unselected = CreateNote(store)(
        CreateNoteCommand(actor, notebook, "Hidden", _content("private"))
    )
    dsn = _scratch_dsn()
    assert dsn is not None
    grounding = PgGroundingStore(make_engine(dsn.replace("postgresql://", "postgresql+psycopg://")))
    request = GroundingRequest(
        actor_user_id=actor,
        notebook_id=notebook,
        conversation_id=uuid.uuid4(),
        question="Use my selected note",
        selected_note_revision_ids=(selected.revision.revision_id,),
    )

    # When
    manifest = grounding.freeze(request=request, normalized_question=request.question)

    # Then
    assert tuple(context.revision_id for context in manifest.note_contexts) == (
        selected.revision.revision_id,
    )
    assert unselected.revision.revision_id not in {
        context.revision_id for context in manifest.note_contexts
    }
    context_text = " ".join(context.text for context in manifest.note_contexts)
    assert "visible" in context_text
    assert "new revision" not in context_text
    assert "private" not in context_text
    with pytest.raises(GroundingError):
        _ = grounding.freeze(
            request=GroundingRequest(
                actor_user_id=outsider,
                notebook_id=notebook,
                conversation_id=uuid.uuid4(),
                question="Cross-notebook leak",
                selected_note_revision_ids=(selected.revision.revision_id,),
            ),
            normalized_question="Cross-notebook leak",
        )


def test_chat_uses_selected_revision_without_searching_notes(pg: Db) -> None:
    # Given
    actor = pg.user()
    notebook = pg.notebook(actor)
    conversation = pg.conversation(actor, notebook_id=notebook)
    store = _store()
    selected = CreateNote(store)(
        CreateNoteCommand(actor, notebook, "Selected", _content("visible"))
    )
    _ = EditNote(store)(
        EditNoteCommand(
            actor,
            selected.note.note_id,
            selected.note.etag,
            _content("new revision"),
        )
    )
    unselected = CreateNote(store)(
        CreateNoteCommand(actor, notebook, "Hidden", _content("private"))
    )
    request = GroundingRequest(
        actor_user_id=actor,
        notebook_id=notebook,
        conversation_id=conversation,
        question="Use the selected note",
        selected_source_ids=frozenset(),
        selected_note_revision_ids=(selected.revision.revision_id,),
    )
    dsn = _scratch_dsn()
    assert dsn is not None
    engine = make_engine(dsn.replace("postgresql://", "postgresql+psycopg://"))
    generator = GenerateGroundedAnswer(
        retrieval=Mock(spec=RetrieveChunks),
        completion=FakeGroundingCompletionProvider(),
        store=PgGroundingStore(engine),
    )

    # When
    answer = generator(request)

    # Then
    assert not answer.insufficient_evidence
    assert answer.citations == ()
    assert answer.spans[0].evidence_ids == ("n1",)
    assert "visible" in answer.spans[0].text
    assert "new revision" not in answer.spans[0].text
    assert "private" not in answer.spans[0].text
    assert answer.message_id is not None
    row = pg.conn.execute(
        "SELECT selected_note_refs, citations FROM messages WHERE id = %s",
        (answer.message_id,),
    ).fetchone()
    assert row is not None
    assert row[0] == [str(selected.revision.revision_id)]
    assert row[1] == [
        {
            "evidence_id": "n1",
            "label": "Selected",
            "note_id": str(selected.note.note_id),
            "note_revision_id": str(selected.revision.revision_id),
            "locator_kind": "note_revision",
            "url": f"/api/v1/note-revisions/{selected.revision.revision_id}",
        }
    ]
    assert unselected.revision.revision_id not in {
        uuid.UUID(reference) for reference in row[0]
    }


def test_chat_rejects_duplicate_note_revision_selection(pg: Db) -> None:
    # Given
    actor = pg.user()
    notebook = pg.notebook(actor)
    selected = CreateNote(_store())(
        CreateNoteCommand(actor, notebook, "Selected", _content("visible"))
    )
    revision_id = selected.revision.revision_id
    dsn = _scratch_dsn()
    assert dsn is not None
    grounding = PgGroundingStore(
        make_engine(dsn.replace("postgresql://", "postgresql+psycopg://"))
    )
    request = GroundingRequest(
        actor_user_id=actor,
        notebook_id=notebook,
        conversation_id=uuid.uuid4(),
        question="Reject duplicate selection",
        selected_note_revision_ids=(revision_id, revision_id),
    )

    # When / Then
    with pytest.raises(GroundingError, match="must be unique"):
        _ = grounding.freeze(request=request, normalized_question=request.question)


def test_chat_revalidates_note_access_before_publication(pg: Db) -> None:
    # Given
    owner = pg.user()
    actor = pg.user()
    notebook = pg.notebook(owner)
    pg.membership(notebook, actor, role="editor")
    conversation = pg.conversation(actor, notebook_id=notebook)
    selected = CreateNote(_store())(
        CreateNoteCommand(owner, notebook, "Selected", _content("visible"))
    )
    dsn = _scratch_dsn()
    assert dsn is not None
    engine = make_engine(dsn.replace("postgresql://", "postgresql+psycopg://"))
    grounding = PgGroundingStore(engine)
    generator = GenerateGroundedAnswer(
        retrieval=Mock(spec=RetrieveChunks),
        completion=FakeGroundingCompletionProvider(),
        store=grounding,
    )
    request = GroundingRequest(
        actor_user_id=actor,
        notebook_id=notebook,
        conversation_id=conversation,
        question="Access must survive publication",
        selected_source_ids=frozenset(),
        selected_note_revision_ids=(selected.revision.revision_id,),
    )
    manifest = grounding.freeze(request=request, normalized_question=request.question)

    # When
    _ = pg.conn.execute(
        "DELETE FROM notebook_memberships WHERE notebook_id = %s AND user_id = %s",
        (notebook, actor),
    )

    # Then
    with pytest.raises(GroundingError):
        _ = generator.generate(request, manifest)
