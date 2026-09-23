"""
Per-user study state and private study-session snapshots (STD-01, guide/13).

Study state is MUTABLE per-user interaction data (position, got-it/missed-it,
scores) keyed by (user, artifact version). It is strictly separate from the
shared immutable artifact content: a study action NEVER creates or mutates an
artifact version, and one user's writes can only touch their own row. A study
session snapshot is an immutable, user-private materialization of state at an
exact version (the input to a later private "performance follow-up" in chat).
"""

from __future__ import annotations

import uuid

from milpbooklm_application.artifact_core import (
    ArtifactNotFoundError,
    ArtifactStore,
    StudySnapshotView,
    UserArtifactStateView,
)


class UpdateStudyState:
    """Create-or-update the actor's own study state row (optimistic)."""

    def __init__(self, store: ArtifactStore) -> None:
        """Wire the artifact store."""
        self._store = store

    def __call__(
        self,
        *,
        actor_id: uuid.UUID,
        artifact_version_id: uuid.UUID,
        state: dict[str, object],
        expected_revision: int | None = None,
    ) -> UserArtifactStateView:
        """
        Update the actor's state for the version; never touches other users.

        ``expected_revision`` enables optimistic concurrency (None = unconditional
        upsert for the first write). The version must exist (404 path).
        """
        version = self._store.get_version_by_id(artifact_version_id)
        if version is None:
            raise ArtifactNotFoundError(f"artifact version {artifact_version_id} not found")
        return self._store.upsert_user_state(
            user_id=actor_id,
            artifact_version_id=artifact_version_id,
            state=state,
            expected_revision=expected_revision,
        )


class GetStudyState:
    """Read the actor's own study state for a version (never another user's)."""

    def __init__(self, store: ArtifactStore) -> None:
        """Wire the artifact store."""
        self._store = store

    def __call__(
        self, *, actor_id: uuid.UUID, artifact_version_id: uuid.UUID
    ) -> UserArtifactStateView | None:
        """Return the actor's state row, or None when they have none yet."""
        return self._store.get_user_state(actor_id, artifact_version_id)


class SnapshotStudySession:
    """Materialize an immutable private snapshot of the actor's study state."""

    def __init__(self, store: ArtifactStore) -> None:
        """Wire the artifact store."""
        self._store = store

    def __call__(
        self, *, actor_id: uuid.UUID, artifact_version_id: uuid.UUID
    ) -> StudySnapshotView:
        """
        Freeze the actor's CURRENT state into a private snapshot.

        The snapshot pins the exact version and the state row it was taken from;
        it is immutable and private (the schema forbids any other visibility).
        """
        version = self._store.get_version_by_id(artifact_version_id)
        if version is None:
            raise ArtifactNotFoundError(f"artifact version {artifact_version_id} not found")
        state = self._store.get_user_state(actor_id, artifact_version_id)
        if state is None:
            raise ArtifactNotFoundError("the actor has no study state to snapshot")
        return self._store.create_study_snapshot(
            user_id=actor_id,
            artifact_version_id=artifact_version_id,
            source_state_id=state.state_id,
            snapshot=dict(state.state),
        )
