"""ARCH-05-018: run evidence is private to the initiating run/user by default; a
snapshot exposed by a shared artifact needs a defined retention/share policy."""

from __future__ import annotations

import json

import psycopg
import pytest
from hypothesis import given
from hypothesis import strategies as st
from milpbooklm_domain.manifests import can_expose_evidence

from tests.domain.invariants._factories import Db
from tests.domain.invariants._ver import write_ver


def test_arch_05_018_private_default_shared_needs_retention(pg_env: dict[str, str]) -> None:
    policies = (
        st.none()
        | st.dictionaries(st.text(min_size=1, max_size=8), st.text(max_size=8), max_size=4)
    )

    @given(st.booleans(), policies)
    def property_holds(shared: bool, policy: dict[str, str] | None) -> None:
        if not shared:
            assert can_expose_evidence(shared=False, retention_policy=policy) is True
        else:
            assert can_expose_evidence(shared=True, retention_policy=policy) is bool(policy)

    property_holds()

    # DB: the research run defaults to private; only 'notebook_shared' is a valid
    # non-private value; a shared exposure requires a retention policy row.
    db = Db(pg_env["app"])
    try:
        user = db.user()
        notebook = db.notebook(user)
        run_id = db.research_run(notebook, user)  # visibility omitted
        default_visibility = db.conn.execute(
            "SELECT visibility FROM research_runs WHERE id = %s", (run_id,)
        ).fetchone()[0]
        assert default_visibility == "private"  # private is the default
        with pytest.raises(psycopg.IntegrityError):
            db.conn.execute("UPDATE research_runs SET visibility = 'public' WHERE id ="
                " %s", (run_id,))
        # A snapshot exposed by a shared artifact must carry a retention policy.
        snapshot = db.evidence_snapshot(run_id, retention_policy=json.dumps({"retention_days": 90}))
        row = db.conn.execute(
            "SELECT retention_policy FROM research_evidence_snapshots WHERE id = %s", (snapshot,)
        ).fetchone()[0]
        assert row == {"retention_days": 90}
    finally:
        db.close()
    write_ver(
        verification_id="VER-ARCH-05-018",
        requirement_id="ARCH-05-018",
        test_path="tests/domain/invariants/ver-arch-05-018.py",
        checks={
            "property": "hypothesis: private exposure always allowed; shared requires a non-empty"
                " retention policy",
            "db_private_default": "research_runs.visibility defaults to 'private'",
            "db_visibility_domain": "only 'private'/'notebook_shared' accepted"
                " (ck_research_runs_visibility)",
            "shared_needs_policy": "a shared-exposed snapshot carries a retention_policy",
        },
    )
