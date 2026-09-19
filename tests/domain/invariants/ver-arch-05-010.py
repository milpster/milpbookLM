"""ARCH-05-010: system-generated/source-derived note content MUST retain its exact
content dependencies, keeping the AD-016 purge traversal enforceable."""

from __future__ import annotations

import json
import uuid

import psycopg
import pytest
from hypothesis import given
from hypothesis import strategies as st
from milpbooklm_domain.notes import ContentKind, ContentRef, is_purge_eligible, make_revision

from tests.domain.invariants._factories import Db
from tests.domain.invariants._ver import write_ver


def test_arch_05_010_derived_note_keeps_dependencies(pg_env: dict[str, str]) -> None:
    @given(st.integers(min_value=0, max_value=5))
    def property_holds(count: int) -> None:
        deps = tuple(
            ContentRef(kind=ContentKind.SOURCE_VERSION, id=uuid.uuid4()) for _ in range(count)
        )
        revision = make_revision(
            id=uuid.uuid4(),
            note_id=uuid.uuid4(),
            revision_number=1,
            content={"blocks": []},
            author_user_id=uuid.uuid4(),
            content_dependencies=deps,
        )
        assert is_purge_eligible(revision) is (count > 0)

    property_holds()

    # DB: content_dependencies is NOT NULL with an empty-array default; a derived note
    # revision carries its exact dependencies and they round-trip.
    db = Db(pg_env["app"])
    try:
        user = db.user()
        notebook = db.notebook(user)
        note_id = db.note(notebook, user, kind="derived_from_source")
        dependencies = json.dumps(
            [
                {"kind": "source_version", "id": str(uuid.uuid4())},
                {"kind": "evidence_snapshot", "id": str(uuid.uuid4())},
            ]
        )
        revision_id = db.note_revision(note_id, user, content_dependencies=dependencies)
        row = db.conn.execute(
            "SELECT content_dependencies, kind FROM note_revisions n JOIN notes no ON no.id ="
                " n.note_id "
            "WHERE n.id = %s",
            (revision_id,),
        ).fetchone()
        assert row[0] == json.loads(dependencies)  # exact dependencies retained
        assert row[1] == "derived_from_source"
        default_deps = db.conn.execute(
            "SELECT content_dependencies FROM note_revisions WHERE id = %s", (revision_id,)
        ).fetchone()
        assert default_deps is not None
        # NOT NULL: the column cannot be cleared (purge traversal would lose its basis).
        with pytest.raises(psycopg.IntegrityError):
            db.conn.execute("UPDATE note_revisions SET content_dependencies = NULL WHERE id ="
                " %s", (revision_id,))
    finally:
        db.close()
    write_ver(
        verification_id="VER-ARCH-05-010",
        requirement_id="ARCH-05-010",
        test_path="tests/domain/invariants/ver-arch-05-010.py",
        checks={
            "property": "hypothesis: purge eligibility iff content_dependencies is non-empty",
            "db_dependencies_retained": "derived note revision carries exact content_dependencies"
                " JSONB",
            "not_null": "content_dependencies cannot be set to NULL",
        },
    )
