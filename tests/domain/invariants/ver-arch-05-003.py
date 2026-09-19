"""ARCH-05-003: a source display-title edit is metadata-only; original bytes, upstream
identity, SourceVersion content and historical manifests are untouched."""

from __future__ import annotations

import uuid

from hypothesis import given
from hypothesis import strategies as st
from milpbooklm_domain.sources import (
    Source,
    SourceType,
    SourceVersion,
    apply_display_title_edit,
)

from tests.domain.invariants._factories import Db
from tests.domain.invariants._ver import write_ver


def _random_source() -> tuple[Source, str]:
    return (
        Source(
            id=uuid.uuid4(),
            notebook_id=uuid.uuid4(),
            type=SourceType.PDF,
            origin="https://example.invalid/doc.pdf",
            display_title="Old",
            versions=(
                SourceVersion(
                    id=uuid.uuid4(),
                    source_id=uuid.uuid4(),
                    version_number=1,
                    content_sha256="a" * 64,
                    original_blob_id=uuid.uuid4(),
                    activated=True,
                ),
            ),
        ),
        f"title-{uuid.uuid4().hex[:12]}",
    )


def test_arch_05_003_title_edit_leaves_versions_and_bytes(pg_env: dict[str, str]) -> None:
    @given(st.data())
    def property_holds(data: st.DataObject) -> None:
        source, new_title = _random_source()
        edited = apply_display_title_edit(source, new_title)
        assert edited.display_title == new_title
        assert edited.id == source.id
        assert edited.origin == source.origin
        assert edited.versions == source.versions  # version content byte-identical
        assert edited.availability == source.availability

    property_holds()

    # DB: editing the display title leaves the active version and origin intact.
    db = Db(pg_env["app"])
    try:
        user = db.user()
        notebook = db.notebook(user)
        source_id = db.source(notebook, user)
        version_id = db.source_version(source_id, user, version_number=1, status="active")
        before = db.conn.execute(
            "SELECT content_sha256, status, activated_at IS NOT NULL FROM source_versions WHERE id"
                " = %s",
            (version_id,),
        ).fetchone()
        db.conn.execute("UPDATE sources SET display_title = %s WHERE id ="
            " %s", ("New Title", source_id))
        after = db.conn.execute(
            "SELECT content_sha256, status, activated_at IS NOT NULL FROM source_versions WHERE id"
                " = %s",
            (version_id,),
        ).fetchone()
        row = db.conn.execute(
            "SELECT display_title, origin, type FROM sources WHERE id = %s", (source_id,)
        ).fetchone()
        assert after == before  # version content, status and activation untouched
        assert row[0] == "New Title"
        assert row[1].startswith("origin://")  # upstream identity unchanged
        assert row[2] == "plain_text"
    finally:
        db.close()
    write_ver(
        verification_id="VER-ARCH-05-003",
        requirement_id="ARCH-05-003",
        test_path="tests/domain/invariants/ver-arch-05-003.py",
        checks={
            "property": "hypothesis: display-title edit preserves id/origin/versions/availability",
            "db_title_edit": "sources.display_title updated; source_versions row byte-identical,"
                " origin and type unchanged",
        },
    )
