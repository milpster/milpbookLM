"""PG artifact store: widened status CAS, insert-only versions, per-user state."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from milpbooklm_adapters.artifact_store import PgArtifactStore
from milpbooklm_adapters.db.connections import make_engine
from milpbooklm_application.artifact_core import (
    ArtifactStateConflictError,
    ArtifactVersionView,
)
from milpbooklm_domain.artifacts import ArtifactStatus
from milpbooklm_domain.manifests import ManifestItem
from milpbooklm_domain.notes import ContentKind

from tests.domain.invariants._factories import Db


def _scratch_dsn() -> str | None:
    socket_dir = Path("scratch/t13-smoke")
    if not (socket_dir / ".s.PGSQL.29521").exists():
        return None
    return (
        "postgresql://milpbooklm_app:milpbooklm_app@/milpbooklm_t13"
        f"?host={socket_dir.resolve()}&port=29521"
    )


@pytest.fixture(name="pg")
def _pg() -> Db | None:
    dsn = _scratch_dsn()
    if dsn is None:
        pytest.skip("live PostgreSQL acceptance stack is not running")
    return Db(dsn)


def _store() -> PgArtifactStore:
    dsn = _scratch_dsn().replace("postgresql://", "postgresql+psycopg://")  # type: ignore[union-attr]
    return PgArtifactStore(make_engine(dsn))


def _draft_artifact(
    pg: Db, artifact_id: uuid.UUID, notebook_id: uuid.UUID, actor: uuid.UUID
) -> None:
    pg.conn.execute(
        "INSERT INTO artifacts (id, notebook_id, artifact_type, created_by_user_id) "
        "VALUES (%s, %s, 'composite', %s)",
        (artifact_id, notebook_id, actor),
    )
    pg.track("DELETE FROM artifacts WHERE id = %s", (artifact_id,))


def test_widened_status_constraint_accepts_full_lifecycle(pg: Db) -> None:
    """0009: draft -> generating -> validating -> ready is legal at the schema level."""
    actor = pg.user()
    notebook = pg.notebook(actor)
    artifact_id = uuid.uuid4()
    _draft_artifact(pg, artifact_id, notebook, actor)
    store = _store()

    expected_from = [ArtifactStatus.DRAFT, ArtifactStatus.GENERATING, ArtifactStatus.VALIDATING]
    for index, target in enumerate(
        (ArtifactStatus.GENERATING, ArtifactStatus.VALIDATING, ArtifactStatus.READY)
    ):
        moved = store.cas_status(artifact_id, expected_from[index], target)
        assert moved is not None
        assert moved.status is target
    # Stale CAS loses: the row is READY, not DRAFT.
    assert store.cas_status(artifact_id, ArtifactStatus.DRAFT, ArtifactStatus.GENERATING) is None


def test_versions_are_insert_only(pg: Db) -> None:
    actor = pg.user()
    notebook = pg.notebook(actor)
    artifact_id = uuid.uuid4()
    _draft_artifact(pg, artifact_id, notebook, actor)
    manifest_id = pg.manifest(notebook_id=notebook, created_by=actor, op_kind="studio_generation")
    version_id = pg.artifact_version(artifact_id, manifest_id, actor)
    store = _store()
    loaded = store.get_version(artifact_id, 1)
    assert loaded is not None
    assert loaded.version_id == version_id
    engine = make_engine(
        _scratch_dsn().replace("postgresql://", "postgresql+psycopg://")  # type: ignore[union-attr]
    )
    with (
        engine.begin() as connection,
        pytest.raises(sa.exc.StatementError),
    ):
        connection.execute(
            sa.text("UPDATE artifact_versions SET recipe_version = '9' WHERE id = :id"),
            {"id": version_id},
        )
    # The immutability guard blocked the write: the row is byte-for-byte unchanged.
    reloaded = store.get_version(artifact_id, 1)
    assert reloaded is not None
    assert reloaded.recipe_version == "1"


def test_user_state_upsert_is_optimistic(pg: Db) -> None:
    actor = pg.user()
    notebook = pg.notebook(actor)
    artifact_id = uuid.uuid4()
    _draft_artifact(pg, artifact_id, notebook, actor)
    manifest_id = pg.manifest(notebook_id=notebook, created_by=actor)
    version_id = pg.artifact_version(artifact_id, manifest_id, actor)
    store = _store()

    created = store.upsert_user_state(
        user_id=actor, artifact_version_id=version_id, state={"progress": 1}
    )
    assert created.revision == 0
    updated = store.upsert_user_state(
        user_id=actor,
        artifact_version_id=version_id,
        state={"progress": 2},
        expected_revision=created.revision,
    )
    assert updated.revision == 1
    with pytest.raises(ArtifactStateConflictError):
        store.upsert_user_state(
            user_id=actor,
            artifact_version_id=version_id,
            state={"progress": 3},
            expected_revision=created.revision,  # stale
        )
    # Another user's row is independent.
    other = pg.user()
    other_row = store.upsert_user_state(
        user_id=other, artifact_version_id=version_id, state={"progress": 9}
    )
    assert other_row.revision == 0
    assert store.get_user_state(actor, version_id) is not None
    assert store.get_user_state(actor, version_id).state == {"progress": 2}


def test_freeze_manifest_round_trips_items(pg: Db) -> None:
    actor = pg.user()
    notebook = pg.notebook(actor)
    source_id = pg.source(notebook, actor)
    source_version = pg.source_version(source_id, actor)
    store = _store()
    items = (
        ManifestItem(ContentKind.SOURCE_VERSION, source_version),
        ManifestItem(ContentKind.NOTE_REVISION, uuid.uuid4()),
    )
    manifest_id = store.freeze_manifest(
        notebook_id=notebook,
        actor_id=actor,
        config_snapshot={"title": "t", "recipe": "composite_echo"},
        items=items,
    )
    loaded = store.get_manifest_items(manifest_id)
    assert loaded == items


def test_study_snapshot_is_private(pg: Db) -> None:
    actor = pg.user()
    notebook = pg.notebook(actor)
    artifact_id = uuid.uuid4()
    _draft_artifact(pg, artifact_id, notebook, actor)
    manifest_id = pg.manifest(notebook_id=notebook, created_by=actor)
    version_id = pg.artifact_version(artifact_id, manifest_id, actor)
    store = _store()
    state = store.upsert_user_state(
        user_id=actor, artifact_version_id=version_id, state={"progress": 5}
    )
    snapshot = store.create_study_snapshot(
        user_id=actor,
        artifact_version_id=version_id,
        source_state_id=state.state_id,
        snapshot={"progress": 5},
    )
    assert snapshot.visibility == "private"
    assert snapshot.snapshot == {"progress": 5}
    assert snapshot.source_state_id == state.state_id


def test_create_version_persists_provenance_bundle(pg: Db) -> None:
    actor = pg.user()
    notebook = pg.notebook(actor)
    artifact_id = uuid.uuid4()
    _draft_artifact(pg, artifact_id, notebook, actor)
    manifest_id = pg.manifest(notebook_id=notebook, created_by=actor, op_kind="studio_generation")
    source_version = pg.source_version(pg.source(notebook, actor), actor)
    version = ArtifactVersionView(
        version_id=uuid.uuid4(),
        artifact_id=artifact_id,
        version_number=1,
        recipe_id="composite_echo",
        recipe_version="1.0.0",
        manifest_id=manifest_id,
        structured_representation={"schema_version": 2, "title": "t", "sections": []},
        rendered_blob_ids=[],
        evidence_dependencies=[{"kind": "source_version", "id": str(source_version)}],
        composite_dependencies=[],
        model_metadata={
            "provider_calls": [],
            "safety_status": "safe",
            "effective_restrictions": {},
        },
        created_by_user_id=actor,
        created_at=None,
    )
    store = _store()
    store.create_version(version)
    loaded = store.get_version_by_id(version.version_id)
    assert loaded is not None
    assert loaded.recipe_id == "composite_echo"
    assert loaded.manifest_id == manifest_id
    assert loaded.evidence_dependencies == version.evidence_dependencies
    assert loaded.model_metadata is not None
    assert loaded.model_metadata["safety_status"] == "safe"
    listed = store.list_versions(artifact_id)
    assert [v.version_number for v in listed] == [1]
