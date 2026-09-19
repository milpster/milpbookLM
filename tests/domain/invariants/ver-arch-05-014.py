"""ARCH-05-014: study mode operates on an immutable, user-private snapshot that pins
the exact artifact version captured; later artifact revisions never leak into it."""

from __future__ import annotations

import uuid

import psycopg
import pytest
from milpbooklm_domain.study import (
    ArtifactVersion,
    UserArtifactState,
    materialize_study_snapshot,
)

from tests.domain.invariants._factories import Db
from tests.domain.invariants._ver import write_ver

PINNED_VERSION_NUMBER = 3


def test_arch_05_014_study_snapshot_immutable_private_pinned(pg_env: dict[str, str]) -> None:
    # Domain: materialization pins the exact version (id, number, sha).
    state = UserArtifactState(user_id=uuid.uuid4(), artifact_version_id=uuid.uuid4(), progress=0.9)
    version = ArtifactVersion(
        id=state.artifact_version_id,
        artifact_id=uuid.uuid4(),
        version_number=PINNED_VERSION_NUMBER,
        content={"cards": [1, 2, 3]},
        manifest_id=uuid.uuid4(),
        content_sha256="d" * 64,
    )
    snapshot = materialize_study_snapshot(state, version)
    assert snapshot.owner_user_id == state.user_id
    assert snapshot.artifact_version_id == version.id
    assert snapshot.version_number == PINNED_VERSION_NUMBER
    assert snapshot.content_sha256 == version.content_sha256
    with pytest.raises(AttributeError):  # frozen: the snapshot cannot be re-pinned
        snapshot.version_number = 4  # type: ignore[misc]

    # DB: the snapshot row is immutable, private-only, and pins the exact version.
    db = Db(pg_env["app"])
    try:
        user = db.user()
        notebook = db.notebook(user)
        manifest = db.manifest(op_kind="studio_generation", notebook_id=notebook, created_by=user)
        artifact = db.artifact(notebook, user)
        version_id = db.artifact_version(
            artifact, manifest, user, version_number=PINNED_VERSION_NUMBER
        )
        state_id = db.user_artifact_state(user, version_id)
        snapshot_id = db.study_snapshot(user, version_id, state_id)

        with pytest.raises(psycopg.Error):  # immutability trigger
            db.conn.execute("UPDATE study_session_snapshots SET snapshot = %s WHERE id ="
                " %s", ('{"progress": 0}', snapshot_id))
        # The BEFORE UPDATE immutability trigger fires before the visibility check.
        with pytest.raises(psycopg.Error):
            db.conn.execute("UPDATE study_session_snapshots SET visibility = 'shared' WHERE id ="
                " %s", (snapshot_id,))
        row = db.conn.execute(
            "SELECT visibility, artifact_version_id, source_state_id FROM study_session_snapshots"
                " WHERE id = %s",
            (snapshot_id,),
        ).fetchone()
        assert row[0] == "private"
        assert row[1] == version_id  # pinned to the exact captured version
        assert row[2] == state_id
    finally:
        db.close()
    write_ver(
        verification_id="VER-ARCH-05-014",
        requirement_id="ARCH-05-014",
        test_path="tests/domain/invariants/ver-arch-05-014.py",
        checks={
            "pins_exact_version": "materialize_study_snapshot captures version id/number/sha;"
                " snapshot is frozen",
            "db_immutable": "snapshot UPDATE rejected by trg_study_session_snapshots_immutable",
            "db_private_only": "visibility stays 'private'; any change rejected",
            "db_pinned": "snapshot pins artifact_version_id and source_state_id",
        },
    )
