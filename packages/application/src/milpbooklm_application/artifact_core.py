"""
Artifact persistence port and logical views (STD-01, guide/13 Storage).

No framework types cross this port: adapters translate the PostgreSQL
``artifacts`` / ``artifact_versions`` / ``user_artifact_state`` /
``study_session_snapshots`` rows (plus the shared ``generation_input_manifests``
pinning) into these pure value objects.

Separation invariants enforced by the port's shape:
* versions are INSERT-only here - there is deliberately no update/delete method
  for ``artifact_versions`` (immutability is the contract, mirrored by the
  schema trigger);
* user state is the only mutable per-user surface, keyed by (user, version) and
  updated under an optimistic revision;
* study snapshots are immutable and private by construction.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from milpbooklm_domain.artifacts import ArtifactStatus, ArtifactType
from milpbooklm_domain.manifests import ManifestItem


class ArtifactError(RuntimeError):
    """Base class for typed artifact failures."""


class ArtifactNotFoundError(LookupError):
    """The artifact (or version/state) is unknown or outside the actor's scope."""


class ArtifactCasConflictError(RuntimeError):
    """A lifecycle compare-and-swap lost the race (concurrent writer)."""


class ArtifactStateConflictError(RuntimeError):
    """A per-user state write lost its optimistic-concurrency CAS (etag/revision)."""


class InvalidArtifactRequestError(ValueError):
    """The request violates the recipe contract or framework rules."""


class ArtifactNotReadyForActionError(RuntimeError):
    """The artifact is in a status that does not admit the requested action."""


@dataclass(frozen=True, slots=True)
class ArtifactView:
    """The logical artifact row (mutable status/pointer; versions live separately)."""

    artifact_id: uuid.UUID
    notebook_id: uuid.UUID
    artifact_type: ArtifactType
    status: ArtifactStatus
    current_version_id: uuid.UUID | None
    created_by_user_id: uuid.UUID
    revision: int
    etag: str
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class ArtifactVersionView:
    """
    One immutable published version (insert-only; never mutated by the port).

    ``model_metadata`` carries the provenance bundle: provider calls, safety
    status and the effective restrictions evaluated at generation time.
    """

    version_id: uuid.UUID
    artifact_id: uuid.UUID
    version_number: int
    recipe_id: str
    recipe_version: str
    manifest_id: uuid.UUID
    structured_representation: dict[str, object] | None
    rendered_blob_ids: list[uuid.UUID]
    evidence_dependencies: list[dict[str, object]]
    composite_dependencies: list[dict[str, object]]
    model_metadata: dict[str, object] | None
    created_by_user_id: uuid.UUID
    created_at: datetime | None


@dataclass(frozen=True, slots=True)
class UserArtifactStateView:
    """One mutable per-user state row, isolated per (user, artifact version)."""

    state_id: uuid.UUID
    user_id: uuid.UUID
    artifact_version_id: uuid.UUID
    state: dict[str, object]
    completed_at: datetime | None
    revision: int


@dataclass(frozen=True, slots=True)
class StudySnapshotView:
    """One immutable, user-private materialization of study state at a version."""

    snapshot_id: uuid.UUID
    user_id: uuid.UUID
    artifact_version_id: uuid.UUID
    source_state_id: uuid.UUID
    snapshot: dict[str, object]
    visibility: str
    created_at: datetime | None


class ArtifactStore(Protocol):
    """Durable persistence for the artifact framework (STD-01)."""

    def create_artifact(self, artifact: ArtifactView) -> None:
        """Insert the logical artifact row in its initial (draft) status."""
        ...

    def get_artifact(self, artifact_id: uuid.UUID) -> ArtifactView | None:
        """Load the logical artifact (None when absent)."""
        ...

    def cas_status(
        self,
        artifact_id: uuid.UUID,
        expected: ArtifactStatus,
        target: ArtifactStatus,
        *,
        field_updates: dict[str, object] | None = None,
    ) -> ArtifactView | None:
        """CAS the lifecycle status; None when the expected status no longer holds."""
        ...

    def freeze_manifest(
        self,
        *,
        notebook_id: uuid.UUID,
        actor_id: uuid.UUID,
        config_snapshot: dict[str, object],
        items: tuple[ManifestItem, ...],
        parent_manifest_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        """Freeze the exact generation inputs; return the immutable manifest id."""
        ...

    def get_manifest_items(self, manifest_id: uuid.UUID) -> tuple[ManifestItem, ...]:
        """Load a manifest's frozen items (provenance for export revalidation)."""
        ...

    def create_version(self, version: ArtifactVersionView) -> None:
        """Insert one immutable version row (the publish step; insert-only)."""
        ...

    def get_version(
        self, artifact_id: uuid.UUID, version_number: int
    ) -> ArtifactVersionView | None:
        """Load one version by (artifact, number); None when absent."""
        ...

    def get_version_by_id(self, version_id: uuid.UUID) -> ArtifactVersionView | None:
        """Load one version by id; None when absent."""
        ...

    def list_versions(self, artifact_id: uuid.UUID) -> list[ArtifactVersionView]:
        """All published versions in version_number order (prior versions retained)."""
        ...

    def get_user_state(
        self, user_id: uuid.UUID, artifact_version_id: uuid.UUID
    ) -> UserArtifactStateView | None:
        """Load the actor's own state row for a version; None when absent."""
        ...

    def upsert_user_state(
        self,
        *,
        user_id: uuid.UUID,
        artifact_version_id: uuid.UUID,
        state: dict[str, object],
        expected_revision: int | None = None,
    ) -> UserArtifactStateView:
        """
        Create-or-update the actor's own state row under optimistic concurrency.

        ``expected_revision`` (when given) must match the stored revision, else
        :class:`ArtifactStateConflictError` - a collaborator's writes never touch
        another user's row (the row is uniquely keyed per (user, version)).
        """
        ...

    def create_study_snapshot(
        self,
        *,
        user_id: uuid.UUID,
        artifact_version_id: uuid.UUID,
        source_state_id: uuid.UUID,
        snapshot: dict[str, object],
    ) -> StudySnapshotView:
        """Materialize one immutable private snapshot of the actor's state."""
        ...
