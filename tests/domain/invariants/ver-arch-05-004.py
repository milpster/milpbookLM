"""ARCH-05-004: losing connector access makes a source ineligible for NEW
retrieval/generation; retained SourceVersions survive (history is preserved)."""

from __future__ import annotations

import uuid

from hypothesis import given
from hypothesis import strategies as st
from milpbooklm_domain.sources import (
    Availability,
    Source,
    SourceType,
    SourceVersion,
    eligible_for_retrieval,
    losing_connector_access,
)

from tests.domain.invariants._factories import SHA256_HEX_LEN, Db
from tests.domain.invariants._ver import write_ver


def _connector_source(availability: Availability) -> Source:
    return Source(
        id=uuid.uuid4(),
        notebook_id=uuid.uuid4(),
        type=SourceType.CONNECTOR,
        origin="connector://drive",
        display_title="Connector doc",
        availability=availability,
        versions=(
            SourceVersion(
                id=uuid.uuid4(),
                source_id=uuid.uuid4(),
                version_number=1,
                content_sha256="b" * 64,
                original_blob_id=uuid.uuid4(),
                activated=True,
            ),
        ),
    )


def test_arch_05_004_inaccessibility_keeps_versions(pg_env: dict[str, str]) -> None:
    @given(st.sampled_from(list(Availability)))
    def property_holds(availability: Availability) -> None:
        source = _connector_source(availability)
        eligible = availability in (Availability.ACTIVE, Availability.STALE)
        assert eligible_for_retrieval(source) is eligible
        revoked = losing_connector_access(source)
        assert revoked.availability is Availability.INACCESSIBLE_REVOKED
        assert revoked.versions == source.versions  # versions survive the revocation

    property_holds()

    # DB: flipping availability keeps every version row (same checksums, activation intact).
    db = Db(pg_env["app"])
    try:
        user = db.user()
        notebook = db.notebook(user)
        source_id = db.source(notebook, user)
        db.source_version(source_id, user, version_number=1, status="active")
        db.source_version(source_id, user, version_number=2, status="activating")
        db.conn.execute("UPDATE sources SET availability = 'inaccessible_revoked' WHERE id ="
            " %s", (source_id,))
        availability = db.conn.execute(
            "SELECT availability FROM sources WHERE id = %s", (source_id,)
        ).fetchone()[0]
        versions = db.conn.execute(
            "SELECT status, content_sha256 FROM source_versions WHERE source_id = %s ORDER BY"
                " version_number",
            (source_id,),
        ).fetchall()
        assert availability == "inaccessible_revoked"
        assert versions[0][0] == "active"
        assert versions[1][0] == "activating"
        assert all(len(row[1]) == SHA256_HEX_LEN for row in versions)  # checksums survive
    finally:
        db.close()
    write_ver(
        verification_id="VER-ARCH-05-004",
        requirement_id="ARCH-05-004",
        test_path="tests/domain/invariants/ver-arch-05-004.py",
        checks={
            "property": "hypothesis: eligibility = {active, stale}; revocation keeps every version",
            "db_inaccessibility": "availability=inaccessible_revoked with both version rows intact",
        },
    )
