"""E2E-004 note journey through HTTP, PostgreSQL, promotion, and chat context."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from milpbooklm_adapters.db.connections import make_engine
from milpbooklm_adapters.grounding import PgGroundingStore
from milpbooklm_adapters.grounding_completion import FakeGroundingCompletionProvider
from milpbooklm_adapters.note_store import PgNoteStore
from milpbooklm_adapters.security.clock import SystemClock
from milpbooklm_adapters.security.fakes import InMemoryAuditLog, InMemoryNotebookReader
from milpbooklm_api.deps import ApiDeps, NoteDeps
from milpbooklm_api.note_routes import build_note_router
from milpbooklm_api.security import ActiveUsersTracker, Principal
from milpbooklm_application.grounding import GenerateGroundedAnswer, GroundingRequest
from milpbooklm_application.note_core import NoteRevisionView, NoteTransformKind
from milpbooklm_application.note_lifecycle import (
    CreateNote,
    EditNote,
    PromoteNoteToSource,
    SaveResponseToNote,
    TransformNotes,
)
from milpbooklm_application.policy_engine import PolicyEngine
from milpbooklm_application.ports import NotebookView
from milpbooklm_application.retrieval import RetrieveChunks
from milpbooklm_application.source_acquisition import AcquireSourceCommand, SourceView
from milpbooklm_domain.identity import User, UserStatus
from milpbooklm_domain.ownership import MembershipRole
from milpbooklm_domain.sources import Availability, SourceType
from starlette import status

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


@dataclass(slots=True)
class _Transformer:
    seen: tuple[uuid.UUID, ...] = ()

    def transform(
        self, kind: NoteTransformKind, revisions: tuple[NoteRevisionView, ...]
    ) -> dict[str, object]:
        self.seen = tuple(revision.revision_id for revision in revisions)
        return {
            "blocks": [
                {
                    "type": "paragraph",
                    "text": f"{kind.value}: {len(revisions)} selected",
                }
            ]
        }


@dataclass(slots=True)
class _Ingestion:
    source: SourceView
    payload: bytes = b""

    async def __call__(
        self, command: AcquireSourceCommand, chunks: AsyncIterable[bytes]
    ) -> tuple[SourceView, bool, uuid.UUID]:
        del command
        collected = bytearray()
        async for chunk in chunks:
            collected.extend(chunk)
        self.payload = bytes(collected)
        return self.source, True, uuid.uuid4()


def _api_deps(reader: InMemoryNotebookReader) -> ApiDeps:
    return ApiDeps(
        users=Mock(),
        sessions=Mock(),
        register=Mock(),
        login=Mock(),
        rotate=Mock(),
        logout=Mock(),
        custody=Mock(),
        audit=InMemoryAuditLog(),
        notebooks=reader,
        engine=PolicyEngine(),
        settings=Mock(),
        clock=Mock(),
        active_users=ActiveUsersTracker(SystemClock()),
        login_limiter=Mock(),
        register_limiter=Mock(),
    )


def _principal(user_id: uuid.UUID, email: str) -> Principal:
    user = User(
        id=user_id,
        email=email,
        display_name=email,
        status=UserStatus.ACTIVE,
        installation_admin=False,
        created_at=datetime.now(UTC),
    )
    return Principal(user, uuid.uuid4(), "token", "csrf")


def test_e2e_004_notes_journey_is_revision_pinned_and_policy_checked(  # noqa: PLR0915
    pg: Db,
) -> None:
    # Given
    actor = pg.user()
    viewer = pg.user()
    notebook = pg.notebook(actor)
    pg.membership(notebook, viewer, role="viewer")
    source_id = pg.source(notebook, actor)
    source_version_id = pg.source_version(source_id, actor)
    source = SourceView(
        source_id,
        source_version_id,
        notebook,
        SourceType.PLAIN_TEXT,
        "Promoted note",
        Availability.ACTIVE,
        "a" * 64,
        5,
        "activating",
        "0",
        uuid.uuid4(),
    )
    dsn = _scratch_dsn()
    assert dsn is not None
    engine = make_engine(dsn.replace("postgresql://", "postgresql+psycopg://"))
    store = PgNoteStore(engine)
    transformer = _Transformer()
    ingestion = _Ingestion(source)
    note_deps = NoteDeps(
        store=store,
        create=CreateNote(store),
        edit=EditNote(store),
        save_response=SaveResponseToNote(store),
        transform=TransformNotes(store, transformer),
        promote=PromoteNoteToSource(store, ingestion),
    )
    reader = InMemoryNotebookReader()
    reader.add_view(
        actor,
        NotebookView(notebook, "Notes", "none", MembershipRole.OWNER),
    )
    reader.add_view(
        viewer,
        NotebookView(notebook, "Notes", "none", MembershipRole.VIEWER),
    )
    active_principal = [_principal(actor, "owner@example.invalid")]

    async def resolve_principal(_request: Request) -> Principal:
        return active_principal[0]

    app = FastAPI()
    app.include_router(build_note_router(_api_deps(reader), resolve_principal, note_deps))
    client = TestClient(app)
    manifest_id = pg.manifest(notebook_id=notebook, created_by=actor)
    conversation_id = pg.conversation(actor, notebook_id=notebook)
    response_id = pg.message(
        conversation_id,
        manifest_id,
        role="assistant",
        content="saved private response",
    )

    # When
    created = client.post(
        f"/api/v1/notebooks/{notebook}/notes",
        json={
            "title": "Draft",
            "content": {"blocks": [{"type": "paragraph", "text": "version one"}]},
        },
    )
    assert created.status_code == status.HTTP_201_CREATED
    created_body = created.json()
    note_id = created_body["note"]["note_id"]
    first_revision_id = created_body["revision"]["revision_id"]
    edited = client.post(
        f"/api/v1/notes/{note_id}/revisions",
        headers={"If-Match": created_body["note"]["etag"]},
        json={
            "content": {"blocks": [{"type": "paragraph", "text": "version two"}]}
        },
    )
    transformed = client.post(
        f"/api/v1/notebooks/{notebook}/notes/transforms",
        json={
            "revision_ids": [first_revision_id],
            "kind": "summarize",
            "title": "Summary",
        },
    )
    saved = client.post(
        f"/api/v1/notebooks/{notebook}/notes/from-response",
        json={"message_id": str(response_id), "title": "Saved response"},
    )
    promoted = client.post(
        f"/api/v1/note-revisions/{edited.json()['revision']['revision_id']}/promote",
        json={"title": "Promoted note"},
    )

    # Then
    assert edited.status_code == status.HTTP_201_CREATED
    assert transformed.status_code == status.HTTP_201_CREATED
    assert saved.status_code == status.HTTP_201_CREATED
    assert saved.json()["note"]["editable"] is False
    assert promoted.status_code == status.HTTP_201_CREATED
    assert promoted.json()["source_version_id"] == str(source_version_id)
    assert transformer.seen == (uuid.UUID(first_revision_id),)
    assert b"version two" in ingestion.payload
    revisions = client.get(f"/api/v1/notes/{note_id}/revisions").json()["revisions"]
    assert [revision["revision_number"] for revision in revisions] == [1, 2]
    assert revisions[0]["content"]["blocks"][0]["text"] == "version one"

    transformed_revision_id = transformed.json()["revision"]["revision_id"]
    answer = GenerateGroundedAnswer(
        retrieval=Mock(spec=RetrieveChunks),
        completion=FakeGroundingCompletionProvider(),
        store=PgGroundingStore(engine),
    )(
        GroundingRequest(
            actor_user_id=actor,
            notebook_id=notebook,
            conversation_id=conversation_id,
            question="Use only my summary",
            selected_source_ids=frozenset(),
            selected_note_revision_ids=(uuid.UUID(transformed_revision_id),),
        )
    )
    assert answer.spans[0].evidence_ids == ("n1",)
    assert "summarize" in answer.spans[0].text
    assert "saved private response" not in answer.spans[0].text

    active_principal[0] = _principal(viewer, "viewer@example.invalid")
    denied = client.post(
        f"/api/v1/notebooks/{notebook}/notes",
        json={
            "title": "Denied",
            "content": {"blocks": [{"type": "paragraph", "text": "denied"}]},
        },
    )
    assert denied.status_code == status.HTTP_403_FORBIDDEN
    assert denied.json() == {"detail": {"reason": "deny:role"}}


def _conflict_client(actor: uuid.UUID, notebook: uuid.UUID) -> TestClient:
    """Wire the real note router over the live store for conflict-path tests."""
    dsn = _scratch_dsn()
    assert dsn is not None
    engine = make_engine(dsn.replace("postgresql://", "postgresql+psycopg://"))
    store = PgNoteStore(engine)
    note_deps = NoteDeps(
        store=store,
        create=CreateNote(store),
        edit=EditNote(store),
        save_response=SaveResponseToNote(store),
        transform=TransformNotes(store, _Transformer()),
        promote=PromoteNoteToSource(store, Mock()),
    )
    reader = InMemoryNotebookReader()
    reader.add_view(
        actor,
        NotebookView(notebook, "Notes", "none", MembershipRole.OWNER),
    )

    async def resolve_principal(_request: Request) -> Principal:
        return _principal(actor, "owner@example.invalid")

    app = FastAPI()
    app.include_router(build_note_router(_api_deps(reader), resolve_principal, note_deps))
    return TestClient(app)


def test_stale_if_match_edit_returns_409_note_conflict(pg: Db) -> None:
    # Given
    actor = pg.user()
    notebook = pg.notebook(actor)
    client = _conflict_client(actor, notebook)
    created = client.post(
        f"/api/v1/notebooks/{notebook}/notes",
        json={
            "title": "Draft",
            "content": {"blocks": [{"type": "paragraph", "text": "version one"}]},
        },
    )
    assert created.status_code == status.HTTP_201_CREATED
    body = created.json()
    stale_etag = body["note"]["etag"]
    first_edit = client.post(
        f"/api/v1/notes/{body['note']['note_id']}/revisions",
        headers={"If-Match": stale_etag},
        json={
            "content": {"blocks": [{"type": "paragraph", "text": "version two"}]},
        },
    )
    assert first_edit.status_code == status.HTTP_201_CREATED

    # When: the superseded etag is reused
    conflicted = client.post(
        f"/api/v1/notes/{body['note']['note_id']}/revisions",
        headers={"If-Match": stale_etag},
        json={
            "content": {"blocks": [{"type": "paragraph", "text": "stale write"}]},
        },
    )

    # Then: the typed conflict survives the transaction exit — 409, not 500
    assert conflicted.status_code == status.HTTP_409_CONFLICT
    assert conflicted.json()["code"] == "note_conflict"


def test_non_editable_note_edit_returns_409_not_editable(pg: Db) -> None:
    # Given
    actor = pg.user()
    notebook = pg.notebook(actor)
    manifest = pg.manifest(notebook_id=notebook, created_by=actor)
    conversation = pg.conversation(actor, notebook_id=notebook)
    message = pg.message(
        conversation, manifest, role="assistant", content="saved private response"
    )
    client = _conflict_client(actor, notebook)
    saved = client.post(
        f"/api/v1/notebooks/{notebook}/notes/from-response",
        json={"message_id": str(message), "title": "Saved"},
    )
    assert saved.status_code == status.HTTP_201_CREATED
    saved_body = saved.json()

    # When
    edited = client.post(
        f"/api/v1/notes/{saved_body['note']['note_id']}/revisions",
        headers={"If-Match": saved_body["note"]["etag"]},
        json={
            "content": {"blocks": [{"type": "paragraph", "text": "attempt"}]},
        },
    )

    # Then
    assert edited.status_code == status.HTTP_409_CONFLICT
    assert edited.json()["code"] == "note_not_editable"
