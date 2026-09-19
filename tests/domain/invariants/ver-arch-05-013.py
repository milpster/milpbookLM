"""ARCH-05-013: two users studying the same artifact version concurrently never
cross-mutate - each session touches only its own isolated state row."""

from __future__ import annotations

import json
import threading
import uuid

import psycopg

from tests.domain.invariants._factories import Db
from tests.domain.invariants._ver import write_ver

STEPS = 25


def _worker(dsn: str, state_id: uuid.UUID, owner: str, errors: list[BaseException]) -> None:
    """One session: increment only its own state row, committing each step."""
    try:
        with psycopg.connect(dsn) as conn:
            for step in range(1, STEPS + 1):
                conn.execute(
                    "UPDATE user_artifact_state SET state = %s::jsonb WHERE id = %s",
                    (json.dumps({"progress": step, "owner": owner}), state_id),
                )
                conn.commit()
    except BaseException as exc:
        errors.append(exc)


def test_arch_05_013_two_users_concurrent_no_cross_mutation(pg_env: dict[str, str]) -> None:
    db = Db(pg_env["app"])
    state_a = state_b = None
    user_a = user_b = None
    try:
        user_a, user_b = db.user(), db.user()
        notebook = db.notebook(user_a)
        db.membership(notebook, user_b, "editor")  # a collaborator studying the same artifact
        manifest = db.manifest(op_kind="studio_generation", notebook_id=notebook, created_by=user_a)
        artifact = db.artifact(notebook, user_a)
        version_id = db.artifact_version(artifact, manifest, user_a)
        state_a = db.user_artifact_state(user_a, version_id)
        state_b = db.user_artifact_state(user_b, version_id)

        errors: list[BaseException] = []
        threads = [
            threading.Thread(target=_worker, args=(pg_env["app"], state_a, "user-a", errors)),
            threading.Thread(target=_worker, args=(pg_env["app"], state_b, "user-b", errors)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert not errors, f"concurrent workers failed: {errors}"

        row_a = db.conn.execute("SELECT state FROM user_artifact_state WHERE id ="
            " %s", (state_a,)).fetchone()[0]
        row_b = db.conn.execute("SELECT state FROM user_artifact_state WHERE id ="
            " %s", (state_b,)).fetchone()[0]
        assert row_a == {"progress": STEPS, "owner": "user-a"}  # own steps only
        assert row_b == {"progress": STEPS, "owner": "user-b"}
        # The shared artifact version was never touched by study actions.
        versions = db.conn.execute(
            "SELECT count(*) FROM artifact_versions WHERE artifact_id = %s", (artifact,)
        ).fetchone()[0]
        assert versions == 1
    finally:
        db.close()
    write_ver(
        verification_id="VER-ARCH-05-013",
        requirement_id="ARCH-05-013",
        test_path="tests/domain/invariants/ver-arch-05-013.py",
        checks={
            "two_sessions": "two real PG sessions (threads) updated their own user_artifact_state"
                " rows concurrently",
            "no_cross_mutation": "each row ended with exactly its own owner marker and full"
                " progress",
            "shared_version_untouched": "the shared artifact version count stayed 1",
        },
    )
