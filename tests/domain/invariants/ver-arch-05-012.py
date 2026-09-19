"""ARCH-05-012: user artifact state is isolated per (user, artifact version) - one
user's study actions only touch their own row and never create artifact versions."""

from __future__ import annotations

import json
import uuid

import psycopg
import pytest
from milpbooklm_domain.study import ArtifactVersion, UserArtifactState, update_user_state

from tests.domain.invariants._factories import Db
from tests.domain.invariants._ver import write_ver


def test_arch_05_012_user_artifact_state_isolated(pg_env: dict[str, str]) -> None:
    # Domain: only the owner of a state row can mutate it.
    version = ArtifactVersion(
        id=uuid.uuid4(),
        artifact_id=uuid.uuid4(),
        version_number=1,
        content={"cards": []},
        manifest_id=uuid.uuid4(),
        content_sha256="c" * 64,
    )
    state = UserArtifactState(user_id=uuid.uuid4(), artifact_version_id=version.id)
    update_user_state(state, user_id=state.user_id, annotations={"card-1": "got-it"})
    with pytest.raises(PermissionError):
        update_user_state(state, user_id=uuid.uuid4(), annotations={"card-1": "got-it"})
    assert version.content == {"cards": []}  # study actions create no new version

    # DB: unique (user, artifact_version); a second row for the same user is rejected;
    # each user's row is independent.
    db = Db(pg_env["app"])
    try:
        user_a, user_b = db.user(), db.user()
        notebook = db.notebook(user_a)
        manifest = db.manifest(op_kind="studio_generation", notebook_id=notebook, created_by=user_a)
        artifact = db.artifact(notebook, user_a)
        version_id = db.artifact_version(artifact, manifest, user_a)
        state_a = db.user_artifact_state(user_a, version_id)
        with pytest.raises(psycopg.IntegrityError):
            db.user_artifact_state(user_a, version_id)  # duplicate (user, version)
        state_b = db.user_artifact_state(user_b, version_id)
        db.conn.execute(
            "UPDATE user_artifact_state SET state = %s, completed_at = now() WHERE id = %s",
            (json.dumps({"progress": 0.4}), state_a),
        )
        row_a = db.conn.execute("SELECT state FROM user_artifact_state WHERE id ="
            " %s", (state_a,)).fetchone()[0]
        row_b = db.conn.execute("SELECT state FROM user_artifact_state WHERE id ="
            " %s", (state_b,)).fetchone()[0]
        assert row_a == {"progress": 0.4}
        assert row_b == {}  # user B's row untouched by user A's actions
    finally:
        db.close()
    write_ver(
        verification_id="VER-ARCH-05-012",
        requirement_id="ARCH-05-012",
        test_path="tests/domain/invariants/ver-arch-05-012.py",
        checks={
            "domain_isolation": "update_user_state raises PermissionError for a non-owner; no new"
                " version created",
            "db_unique_pair": "uq_user_artifact_state_user_version rejects a duplicate (user,"
                " version) row",
            "db_rows_independent": "user A's state update leaves user B's row at the default",
        },
    )
