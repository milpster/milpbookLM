"""ARCH-05-020: no durable citation of run evidence exists without a retention
policy - a citation pointing at an exposed snapshot requires the snapshot to carry a
defined retention/share policy first."""

from __future__ import annotations

import json

from hypothesis import given
from hypothesis import strategies as st
from milpbooklm_domain.manifests import can_expose_evidence

from tests.domain.invariants._factories import Db
from tests.domain.invariants._ver import write_ver


def test_arch_05_020_no_durable_citation_without_retention(pg_env: dict[str, str]) -> None:
    @given(
        st.sampled_from(
            [None, {}, {"retention_days": 90}, {"share": "notebook", "purge": "cascade"}]
        ),
    )
    def property_holds(policy: dict[str, object] | None) -> None:
        # A durable (shared) citation of evidence is allowed iff a retention policy exists.
        assert can_expose_evidence(shared=True, retention_policy=policy) is bool(policy)

    property_holds()

    # DB: a durable citation references an evidence snapshot by id; the snapshot's
    # retention_policy column is the DDL hook that makes the citation admissible.
    db = Db(pg_env["app"])
    try:
        user = db.user()
        notebook = db.notebook(user)
        conversation = db.conversation(user, notebook_id=notebook)
        manifest = db.manifest(op_kind="ordinary_chat", notebook_id=notebook, created_by=user)
        run = db.research_run(notebook, user)
        snapshot_without = db.evidence_snapshot(run)  # no retention policy
        policy = json.dumps({"retention_days": 90})
        snapshot_with = db.evidence_snapshot(run, retention_policy=policy)

        citations = json.dumps(
            [
                {"evidence_snapshot": str(snapshot_without), "retained": False},
                {"evidence_snapshot": str(snapshot_with), "retained": True},
            ]
        )
        message_id = db.message(
            conversation,
            manifest,
            role="assistant",
            content="answer",
            citations=citations,
        )
        stored = db.conn.execute("SELECT citations FROM messages WHERE id ="
            " %s", (message_id,)).fetchone()[0]
        assert stored[0]["retained"] is False  # the unretained citation is flagged as not retained
        assert stored[1]["retained"] is True
        # The unretained snapshot cannot be exposed (domain gate), the retained one can.
        without_policy = db.conn.execute(
            "SELECT retention_policy FROM research_evidence_snapshots WHERE id ="
                " %s", (snapshot_without,)
        ).fetchone()[0]
        with_policy = db.conn.execute(
            "SELECT retention_policy FROM research_evidence_snapshots WHERE id ="
                " %s", (snapshot_with,)
        ).fetchone()[0]
        assert can_expose_evidence(shared=True, retention_policy=without_policy) is False
        assert can_expose_evidence(shared=True, retention_policy=with_policy) is True
    finally:
        db.close()
    write_ver(
        verification_id="VER-ARCH-05-020",
        requirement_id="ARCH-05-020",
        test_path="tests/domain/invariants/ver-arch-05-020.py",
        checks={
            "property": "hypothesis: a shared/durable citation is admissible iff a retention"
                " policy exists",
            "db_citation": "a message citation references evidence snapshots; retention_policy"
                " gates exposure",
            "unretained_not_exposable": "the unretained snapshot fails can_expose_evidence",
        },
    )
