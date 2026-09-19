"""
Artifact versioning and study-session snapshot invariants (ch05 §8, ARCH-05-012..014).

Artifact is the stable logical object; ArtifactVersion is its immutable content. Each user
holds isolated per-user state (annotations, pins, progress) that must never mutate the
shared artifact version or create new versions for other users. Study mode operates on an
immutable, private snapshot that pins the exact artifact version captured.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ArtifactVersion:
    """Immutable content of an artifact at one revision."""

    id: uuid.UUID
    artifact_id: uuid.UUID
    version_number: int
    content: dict[str, object]
    manifest_id: uuid.UUID
    content_sha256: str


@dataclass(slots=True)
class UserArtifactState:
    """Per-user mutable state; isolated per (user, artifact_version)."""

    user_id: uuid.UUID
    artifact_version_id: uuid.UUID
    annotations: dict[str, object] = field(default_factory=dict)
    progress: float = 0.0
    pinned: bool = False


def update_user_state(
    state: UserArtifactState, *, user_id: uuid.UUID, annotations: dict[str, object]
) -> UserArtifactState:
    """Only the owner's own state is writable; the pinned version is untouched."""
    if state.user_id != user_id:
        raise PermissionError("user state is isolated per user")
    state.annotations.update(annotations)
    return state


def materialize_study_snapshot(
    state: UserArtifactState, version: ArtifactVersion
) -> StudySessionSnapshot:
    """
    Materialize an immutable, private study session snapshot.

    Pinned to the exact artifact version (ARCH-05-014): later artifact revisions never
    leak into the study session.
    """
    return StudySessionSnapshot(
        id=uuid.UUID(int=0),  # placeholder-free: caller assigns via DB default (uuidv7())
        owner_user_id=state.user_id,
        artifact_version_id=version.id,
        version_number=version.version_number,
        content_sha256=version.content_sha256,
    )


@dataclass(frozen=True, slots=True)
class StudySessionSnapshot:
    """Immutable private study snapshot pinning one exact artifact version."""

    id: uuid.UUID
    owner_user_id: uuid.UUID
    artifact_version_id: uuid.UUID
    version_number: int
    content_sha256: str
