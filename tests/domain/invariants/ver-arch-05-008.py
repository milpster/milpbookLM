"""ARCH-05-008: a note selected as generation context MUST resolve to an immutable
NoteRevision; the resolved snapshot is unaffected by any later note edit."""

from __future__ import annotations

import uuid

import psycopg
import pytest
from milpbooklm_domain.notes import (
    Note,
    NoteKind,
    make_revision,
    resolve_generation_context,
)

from tests.domain.invariants._factories import SHA256_HEX_LEN, Db
from tests.domain.invariants._ver import write_ver


def test_arch_05_008_generation_context_pins_immutable_revision(pg_env: dict[str, str]) -> None:
    # Domain: resolving the context pins the exact revision; a later edit is a NEW
    # revision and does not touch the pinned snapshot.
    author = uuid.uuid4()
    note_id = uuid.uuid4()
    revision_1 = make_revision(
        id=uuid.uuid4(),
        note_id=note_id,
        revision_number=1,
        content={"blocks": [{"text": "v1"}]},
        author_user_id=author,
    )
    revision_2 = make_revision(
        id=uuid.uuid4(),
        note_id=note_id,
        revision_number=2,
        content={"blocks": [{"text": "v2"}]},
        author_user_id=author,
    )
    note = Note(
        id=note_id,
        notebook_id=uuid.uuid4(),
        kind=NoteKind.USER,
        editable=True,
        title="Research note",
        current_revision_id=revision_1.id,
        revisions=(revision_1,),
    )
    resolved = resolve_generation_context(note, revision_1.id)
    assert resolved is not None
    assert resolved.id == revision_1.id
    edited_note = Note(
        id=note.id,
        notebook_id=note.notebook_id,
        kind=note.kind,
        editable=note.editable,
        title=note.title,
        current_revision_id=revision_2.id,
        revisions=(revision_1, revision_2),
    )
    still_resolved = resolve_generation_context(edited_note, revision_1.id)
    assert still_resolved is not None
    assert still_resolved.content == revision_1.content
    assert still_resolved.content_sha256 == revision_1.content_sha256  # untouched by the edit
    fallback = resolve_generation_context(note, uuid.uuid4())
    assert fallback is None  # unknown id: no implicit fallback

    # DB: note_revisions are immutable (update and delete both rejected by the trigger).
    db = Db(pg_env["app"])
    try:
        user = db.user()
        notebook = db.notebook(user)
        note_db = db.note(notebook, user)
        revision_db = db.note_revision(note_db, user, revision_number=1)
        with pytest.raises(psycopg.Error):
            db.conn.execute("UPDATE note_revisions SET content = %s WHERE id ="
                " %s", ('{"blocks": []}', revision_db))
        with pytest.raises(psycopg.Error):
            db.conn.execute("DELETE FROM note_revisions WHERE id = %s", (revision_db,))
        pinned = db.conn.execute(
            "SELECT content_sha256 FROM note_revisions WHERE id = %s", (revision_db,)
        ).fetchone()[0]
        assert len(pinned) == SHA256_HEX_LEN  # the revision survived both attempts
    finally:
        db.close()
    write_ver(
        verification_id="VER-ARCH-05-008",
        requirement_id="ARCH-05-008",
        test_path="tests/domain/invariants/ver-arch-05-008.py",
        checks={
            "pin_survives_edit": "resolve_generation_context returns the same content/sha before"
                " and after a note edit",
            "no_implicit_fallback": "an unknown selected revision resolves to None",
            "db_immutable": "note_revisions UPDATE and DELETE both rejected by"
                " trg_note_revisions_immutable",
        },
    )
