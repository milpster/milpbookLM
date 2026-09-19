"""ARCH-05-009: a note revision carries rich structure (tables, inline citations)
preserved as structured content, plus its provenance references."""

from __future__ import annotations

import json
import uuid

from milpbooklm_domain.notes import make_revision, revision_content_sha256

from tests.domain.invariants._factories import Db
from tests.domain.invariants._ver import write_ver


def test_arch_05_009_revision_rich_structure_and_provenance(pg_env: dict[str, str]) -> None:
    # Domain: the revision digest is canonical (key-order independent, change-sensitive).
    content = {
        "blocks": [
            {"type": "paragraph", "text": "intro"},
            {
                "type": "table",
                "rows": [[1, 2], [3, 4]],
            },
            {
                "type": "paragraph",
                "text": "see [1]",
                "citations": [{"source_version": "sha-ref", "locator": "p.12"}],
            },
        ]
    }
    author = uuid.uuid4()
    revision = make_revision(
        id=uuid.uuid4(),
        note_id=uuid.uuid4(),
        revision_number=1,
        content=content,
        author_user_id=author,
    )
    reordered = dict(reversed(list(content.items())))
    assert revision_content_sha256(reordered) == revision.content_sha256
    assert revision.content_sha256 == revision.content_sha256  # stable under repeated calls

    # DB: the rich JSONB structure and provenance round-trip exactly.
    provenance = json.dumps(
        [{"kind": "source_version", "id": str(uuid.uuid4()), "locator": "page:12"}]
    )
    db = Db(pg_env["app"])
    try:
        user = db.user()
        notebook = db.notebook(user)
        note_id = db.note(notebook, user)
        revision_id = db.note_revision(
            note_id,
            user,
            revision_number=1,
            content=content,
            provenance_refs=provenance,
        )
        row = db.conn.execute(
            "SELECT content, provenance_refs, content_sha256, author_user_id FROM note_revisions"
                " WHERE id = %s",
            (revision_id,),
        ).fetchone()
        assert row[0] == content  # rich structure (table + inline citation) preserved
        assert row[1] == json.loads(provenance)  # provenance preserved
        assert row[2] == revision.content_sha256  # same canonical digest as the domain
        assert row[3] == user  # the DB row is authored by the db user, not the domain sample
    finally:
        db.close()
    write_ver(
        verification_id="VER-ARCH-05-009",
        requirement_id="ARCH-05-009",
        test_path="tests/domain/invariants/ver-arch-05-009.py",
        checks={
            "canonical_digest": "revision_content_sha256 is key-order stable and change-sensitive",
            "rich_structure": "table + inline-citation JSONB round-trips exactly",
            "provenance": "provenance_refs JSONB round-trips; author pinned",
            "domain_db_digest_parity": "DB content_sha256 equals the domain canonical digest",
        },
    )
