"""ARCH-05-017: a run evidence snapshot is immutable once captured (origin, time,
locator, checksum, blob, access metadata); only retention_policy and the one-time
promotion to a SourceVersion may change."""

from __future__ import annotations

import psycopg
import pytest

from tests.domain.invariants._factories import Db
from tests.domain.invariants._ver import write_ver


def test_arch_05_017_evidence_snapshot_immutable_capture(pg_env: dict[str, str]) -> None:
    db = Db(pg_env["app"])
    try:
        user = db.user()
        notebook = db.notebook(user)
        run = db.research_run(notebook, user)
        blob = db.blob(state="finalized")
        snapshot = db.evidence_snapshot(
            run, blob_id=blob, retention_policy='{"retention_days": 90}'
        )

        for column, value in (
            ("origin_tool", "spoofed"),
            ("acquired_at", "epoch"),
            ("content_sha256", "0" * 64),
            ("blob_id", None),
            ("locators", "{}"),
            ("access_metadata", "{}"),
        ):
            with pytest.raises(psycopg.Error):
                db.conn.execute(f"UPDATE research_evidence_snapshots SET {column} = %s WHERE id ="
                    " %s", (value, snapshot))

        # The sanctioned mutables: retention policy and the one-time promotion.
        db.conn.execute(
            "UPDATE research_evidence_snapshots SET retention_policy = %s WHERE id = %s",
            ('{"retention_days": 30}', snapshot),
        )
        user_row = db.user()
        other_notebook = db.notebook(user_row)
        other_source = db.source(other_notebook, user_row)
        promoted = db.source_version(other_source, user_row, version_number=1, status="active")
        db.conn.execute(
            "UPDATE research_evidence_snapshots SET promoted_source_version_id = %s WHERE id = %s",
            (promoted, snapshot),
        )
        row = db.conn.execute(
            "SELECT retention_policy, promoted_source_version_id FROM research_evidence_snapshots"
                " WHERE id = %s",
            (snapshot,),
        ).fetchone()
        assert row[0] == {"retention_days": 30}
        assert row[1] == promoted
        assert blob is not None  # the captured blob reference stayed intact
    finally:
        db.close()
    write_ver(
        verification_id="VER-ARCH-05-017",
        requirement_id="ARCH-05-017",
        test_path="tests/domain/invariants/ver-arch-05-017.py",
        checks={
            "capture_immutable": "capture fields (origin..access_metadata) updates all rejected",
            "sanctioned_mutables": "retention_policy and promoted_source_version_id update"
                " successfully",
        },
    )
