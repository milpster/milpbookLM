"""ARCH-05-011: notes NEVER silently join the ordinary source corpus; note content
enters generation only via explicit selection (a pinned, immutable revision)."""

from __future__ import annotations

import uuid

from hypothesis import given
from hypothesis import strategies as st
from milpbooklm_domain.notes import Note, NoteKind, ordinary_source_corpus_note_ids

from tests.domain.invariants._factories import Db
from tests.domain.invariants._ver import write_ver

KINDS = (NoteKind.USER, NoteKind.SAVED_CHAT_RESPONSE, NoteKind.DERIVED_FROM_SOURCE)


def _note(kind: NoteKind) -> Note:
    return Note(
        id=uuid.uuid4(),
        notebook_id=uuid.uuid4(),
        kind=kind,
        editable=kind is NoteKind.USER,
        title="note",
        current_revision_id=uuid.uuid4(),
    )


def test_arch_05_011_notes_never_in_ordinary_corpus(pg_env: dict[str, str]) -> None:
    @given(st.lists(st.sampled_from(list(KINDS)), min_size=0, max_size=8))
    def property_holds(kinds: list[NoteKind]) -> None:
        notes = tuple(_note(kind) for kind in kinds)
        corpus = ordinary_source_corpus_note_ids(notes)
        assert corpus == frozenset()  # the ordinary corpus contains no note ids, ever
        assert not (corpus & {note.id for note in notes})

    property_holds()

    # DB: notes live in their own tables, separate from sources/source_versions - a
    # note is reachable from the notebook, not from the source corpus.
    db = Db(pg_env["app"])
    try:
        user = db.user()
        notebook = db.notebook(user)
        note_id = db.note(notebook, user)
        revision = db.note_revision(note_id, user)
        db.conn.execute("UPDATE notes SET current_revision_id = %s WHERE id ="
            " %s", (revision, note_id))
        note_in_sources = db.conn.execute(
            "SELECT count(*) FROM sources s WHERE s.notebook_id = %s AND s.id = %s",
            (notebook, note_id),
        ).fetchone()[0]
        note_is_source = db.conn.execute(
            "SELECT count(*) FROM source_versions sv JOIN sources s ON s.id = sv.source_id "
            "WHERE s.id = %s",
            (note_id,),
        ).fetchone()[0]
        assert note_in_sources == 0  # no source row references a note
        assert note_is_source == 0  # a note id is not a source id
    finally:
        db.close()
    write_ver(
        verification_id="VER-ARCH-05-011",
        requirement_id="ARCH-05-011",
        test_path="tests/domain/invariants/ver-arch-05-011.py",
        checks={
            "property": "hypothesis: ordinary_source_corpus_note_ids(notes) is the empty set for"
                " any notebook notes",
            "db_separation": "notes/note_revisions tables are disjoint from"
                " sources/source_versions",
        },
    )
