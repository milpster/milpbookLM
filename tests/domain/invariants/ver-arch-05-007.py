"""ARCH-05-007: a saved chat-response note may be immutable after creation -
editability is a policy carried on the NOTE (kind + editable), not on the revision."""

from __future__ import annotations

import uuid

import psycopg
import pytest
from milpbooklm_domain.notes import Note, NoteKind

from tests.domain.invariants._factories import Db
from tests.domain.invariants._ver import write_ver


def test_arch_05_007_saved_chat_response_not_editable(pg_env: dict[str, str]) -> None:
    # Domain: the kind names the saved chat response; editability is the note's policy.
    assert NoteKind.SAVED_CHAT_RESPONSE.value == "saved_chat_response"
    note = Note(
        id=uuid.uuid4(),
        notebook_id=uuid.uuid4(),
        kind=NoteKind.SAVED_CHAT_RESPONSE,
        editable=False,
        title="Saved answer",
        current_revision_id=uuid.uuid4(),
    )
    assert note.editable is False
    assert note.kind is NoteKind.SAVED_CHAT_RESPONSE

    # DB: the policy is persisted; the note object stays mutable (title) while the
    # revision it pins stays immutable; an unknown kind is rejected.
    db = Db(pg_env["app"])
    try:
        user = db.user()
        notebook = db.notebook(user)
        note_id = db.note(
            notebook, user, kind="saved_chat_response", editable=False, title="Saved answer"
        )
        revision = db.note_revision(note_id, user, revision_number=1)
        db.conn.execute(
            "UPDATE notes SET current_revision_id = %s WHERE id = %s", (revision, note_id)
        )
        row = db.conn.execute(
            "SELECT kind, editable, current_revision_id FROM notes WHERE id = %s", (note_id,)
        ).fetchone()
        assert row[0] == "saved_chat_response"
        assert row[1] is False
        assert row[2] == revision  # the note pins the immutable revision
        # The mutable note object can still be retitled...
        db.conn.execute("UPDATE notes SET title = 'Saved answer (edited)' WHERE id ="
            " %s", (note_id,))
        # ...while the pinned revision is immutable.
        with pytest.raises(psycopg.Error):
            db.conn.execute("UPDATE note_revisions SET content = %s WHERE id ="
                " %s", ('{"blocks": []}', revision))
        with pytest.raises(psycopg.IntegrityError):
            db.conn.execute(
                "INSERT INTO notes (id, notebook_id, kind, editable, title, created_by_user_id) "
                "VALUES (%s, %s, 'bogus_kind', true, 'X', %s)",
                (uuid.uuid4(), notebook, user),
            )
    finally:
        db.close()
    write_ver(
        verification_id="VER-ARCH-05-007",
        requirement_id="ARCH-05-007",
        test_path="tests/domain/invariants/ver-arch-05-007.py",
        checks={
            "domain_policy": "NoteKind.SAVED_CHAT_RESPONSE + Note.editable=False",
            "db_policy_persisted": "kind=saved_chat_response, editable=false, pins"
                " current_revision_id",
            "revision_stays_immutable": "note retitle allowed; pinned note_revisions update"
                " rejected",
            "kind_domain_enforced": "ck_notes_kind rejects an unknown kind",
        },
    )
