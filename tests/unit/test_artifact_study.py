"""Per-user study state isolation and private snapshots (study never touches versions)."""

from __future__ import annotations

import uuid

import pytest
from milpbooklm_application.artifact_core import (
    ArtifactNotFoundError,
    ArtifactStateConflictError,
    ArtifactVersionView,
    ArtifactView,
)
from milpbooklm_application.artifact_study import (
    GetStudyState,
    SnapshotStudySession,
    UpdateStudyState,
)
from milpbooklm_domain.artifacts import ArtifactStatus, ArtifactType

from .test_artifact_lifecycle import FakeArtifactStore


def _version(store: FakeArtifactStore) -> ArtifactVersionView:
    artifact = ArtifactView(
        artifact_id=uuid.uuid4(),
        notebook_id=uuid.uuid4(),
        artifact_type=ArtifactType.COMPOSITE,
        status=ArtifactStatus.READY,
        current_version_id=None,
        created_by_user_id=uuid.uuid4(),
        revision=1,
        etag="1",
        created_at=None,
        updated_at=None,
    )
    version = ArtifactVersionView(
        version_id=uuid.uuid4(),
        artifact_id=artifact.artifact_id,
        version_number=1,
        recipe_id="composite_echo",
        recipe_version="1.0.0",
        manifest_id=uuid.uuid4(),
        structured_representation={"schema_version": 2, "title": "t"},
        rendered_blob_ids=[],
        evidence_dependencies=[],
        composite_dependencies=[],
        model_metadata=None,
        created_by_user_id=artifact.created_by_user_id,
        created_at=None,
    )
    store.create_artifact(artifact)
    store.create_version(version)
    return version


def test_study_state_is_isolated_per_user() -> None:
    store = FakeArtifactStore()
    version = _version(store)
    actor_a, actor_b = uuid.uuid4(), uuid.uuid4()
    update = UpdateStudyState(store)
    update(actor_id=actor_a, artifact_version_id=version.version_id, state={"progress": 1})
    # Actor B never sees A's state.
    assert GetStudyState(store)(actor_id=actor_b, artifact_version_id=version.version_id) is None
    # A's own read returns exactly what A wrote.
    own = GetStudyState(store)(actor_id=actor_a, artifact_version_id=version.version_id)
    assert own is not None
    assert own.state == {"progress": 1}


def test_study_state_write_conflicts_on_stale_revision() -> None:
    store = FakeArtifactStore()
    version = _version(store)
    actor = uuid.uuid4()
    update = UpdateStudyState(store)
    first = update(actor_id=actor, artifact_version_id=version.version_id, state={"progress": 1})
    assert first.revision == 0
    second = update(
        actor_id=actor,
        artifact_version_id=version.version_id,
        state={"progress": 2},
        expected_revision=first.revision,
    )
    assert second.revision == 1
    with pytest.raises(ArtifactStateConflictError):
        update(
            actor_id=actor,
            artifact_version_id=version.version_id,
            state={"progress": 3},
            expected_revision=first.revision,  # stale
        )


def test_snapshot_freezes_state_is_private_and_never_creates_versions() -> None:
    store = FakeArtifactStore()
    version = _version(store)
    actor = uuid.uuid4()
    UpdateStudyState(store)(
        actor_id=actor, artifact_version_id=version.version_id, state={"progress": 3}
    )
    snapshot = SnapshotStudySession(store)(actor_id=actor, artifact_version_id=version.version_id)
    assert snapshot.visibility == "private"
    assert snapshot.snapshot == {"progress": 3}
    assert snapshot.source_state_id is not None
    # Study actions NEVER create or mutate artifact versions.
    assert [v.version_number for v in store.list_versions(version.artifact_id)] == [1]


def test_snapshot_requires_existing_state() -> None:
    store = FakeArtifactStore()
    version = _version(store)
    with pytest.raises(ArtifactNotFoundError):
        SnapshotStudySession(store)(actor_id=uuid.uuid4(), artifact_version_id=version.version_id)
