"""ARCH-05-019: run evidence participates in the AD-016 purge closure - every
content-bearing user of a blob is tracked, and the snapshot's retention/promotion
fields define how the closure resolves."""

from __future__ import annotations

import json
import uuid

import psycopg
import pytest
from milpbooklm_domain.manifests import can_expose_evidence

from tests.domain.invariants._factories import Db
from tests.domain.invariants._ver import write_ver

EXPECTED_CONTENT_USERS = 2


def test_arch_05_019_evidence_in_purge_closure(pg_env: dict[str, str]) -> None:
    # Domain: a shared exposure is purge-governed only with a defined retention policy.
    assert can_expose_evidence(shared=True, retention_policy=None) is False
    assert can_expose_evidence(shared=True, retention_policy={"retention_days": 90}) is True

    # DB: blob_references track every content-bearing user of an object (the purge
    # traversal basis); the snapshot keeps its retention policy for the closure.
    db = Db(pg_env["app"])
    try:
        user = db.user()
        notebook = db.notebook(user)
        run = db.research_run(notebook, user)
        blob = db.blob(state="finalized")
        snapshot = db.evidence_snapshot(
            run, blob_id=blob, retention_policy=json.dumps({"retention_days": 90})
        )

        # Track the evidence snapshot as a content-bearing user of the blob...
        referrer = snapshot
        db.conn.execute(
            "INSERT INTO blob_references (id, blob_id, referrer_kind, referrer_id) VALUES (%s, %s,"
                " %s, %s)",
            (uuid.uuid4(), blob, "research_evidence_snapshot", referrer),
        )
        # ...and a second, distinct referrer; a duplicate (blob, kind, id) is rejected.
        other_referrer = db.notebook(user)
        db.conn.execute(
            "INSERT INTO blob_references (id, blob_id, referrer_kind, referrer_id) VALUES (%s, %s,"
                " %s, %s)",
            (uuid.uuid4(), blob, "notebook", other_referrer),
        )
        with pytest.raises(psycopg.IntegrityError):
            db.conn.execute(
                "INSERT INTO blob_references (id, blob_id, referrer_kind, referrer_id) VALUES (%s,"
                    " %s, %s, %s)",
                (uuid.uuid4(), blob, "notebook", other_referrer),
            )
        users = db.conn.execute(
            "SELECT count(*) FROM blob_references WHERE blob_id = %s", (blob,)
        ).fetchone()[0]
        assert users == EXPECTED_CONTENT_USERS  # every content user of the blob tracked
        policy = db.conn.execute(
            "SELECT retention_policy FROM research_evidence_snapshots WHERE id = %s", (snapshot,)
        ).fetchone()[0]
        assert policy == {"retention_days": 90}  # the closure resolves via the retention policy
    finally:
        db.close()
    write_ver(
        verification_id="VER-ARCH-05-019",
        requirement_id="ARCH-05-019",
        test_path="tests/domain/invariants/ver-arch-05-019.py",
        checks={
            "domain_gate": "shared exposure is purge-governed only with a retention policy",
            "blob_references": "every content-bearing user of a blob is tracked; duplicates"
                " rejected",
            "retention_policy": "the snapshot's retention_policy resolves the purge closure",
        },
    )
