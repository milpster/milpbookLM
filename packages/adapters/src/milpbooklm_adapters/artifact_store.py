"""
PostgreSQL implementation of the artifact store port (STD-01).

Follows the research_runs adapter: one transaction per operation, CAS updates
with ``RETURNING``, and the shared generation-manifest tables for input
pinning. ``artifact_versions`` is insert-only here on purpose - the immutability
trigger rejects any UPDATE/DELETE, and edits/regenerations are NEW rows.
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from milpbooklm_application.artifact_core import (
    ArtifactStateConflictError,
    ArtifactVersionView,
    ArtifactView,
    StudySnapshotView,
    UserArtifactStateView,
)
from milpbooklm_domain.artifacts import ArtifactStatus, ArtifactType
from milpbooklm_domain.manifests import ManifestItem
from milpbooklm_domain.notes import ContentKind

from milpbooklm_adapters.db.tables.manifests import (
    generation_input_manifests,
    generation_manifest_items,
)
from milpbooklm_adapters.db.tables.studio import (
    artifact_versions,
    artifacts,
    study_session_snapshots,
    user_artifact_state,
)


class PgArtifactStore:
    """Durable artifacts/versions/state/snapshots persistence with CAS updates."""

    def __init__(self, engine: sa.engine.Engine) -> None:
        """Bind the application-role database engine."""
        self._engine = engine

    def create_artifact(self, artifact: ArtifactView) -> None:
        """Insert the logical artifact row (draft, revision 0)."""
        with self._engine.begin() as connection:
            _ = connection.execute(
                sa.insert(artifacts).values(
                    id=artifact.artifact_id,
                    notebook_id=artifact.notebook_id,
                    artifact_type=artifact.artifact_type.value,
                    status=artifact.status.value,
                    current_version_id=artifact.current_version_id,
                    created_by_user_id=artifact.created_by_user_id,
                    revision=artifact.revision,
                    etag=artifact.etag,
                )
            )

    def get_artifact(self, artifact_id: uuid.UUID) -> ArtifactView | None:
        """Load the logical artifact (None when absent)."""
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(artifacts).where(artifacts.c.id == artifact_id)
                )
                .mappings()
                .one_or_none()
            )
        return _artifact_view(row) if row is not None else None

    def cas_status(
        self,
        artifact_id: uuid.UUID,
        expected: ArtifactStatus,
        target: ArtifactStatus,
        *,
        field_updates: dict[str, object] | None = None,
    ) -> ArtifactView | None:
        """CAS the lifecycle status; None when the expected status no longer holds."""
        updates: dict[str, object] = {
            "status": target.value,
            "revision": artifacts.c.revision + 1,
            "etag": (artifacts.c.revision + 1).cast(sa.String),
        }
        updates.update(field_updates or {})
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    sa.update(artifacts)
                    .where(
                        artifacts.c.id == artifact_id,
                        artifacts.c.status == expected.value,
                    )
                    .values(**updates)
                    .returning(artifacts)
                )
                .mappings()
                .one_or_none()
            )
        return _artifact_view(row) if row is not None else None

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
        manifest_id = uuid.uuid4()
        with self._engine.begin() as connection:
            _ = connection.execute(
                sa.insert(generation_input_manifests).values(
                    id=manifest_id,
                    notebook_id=notebook_id,
                    created_by_user_id=actor_id,
                    op_kind="studio_generation",
                    config_snapshot=config_snapshot,
                    parent_manifest_id=parent_manifest_id,
                )
            )
            for item in items:
                _ = connection.execute(
                    sa.insert(generation_manifest_items).values(
                        id=uuid.uuid4(),
                        manifest_id=manifest_id,
                        item_kind=item.kind.value,
                        item_id=item.item_id,
                        item_sha256=item.item_sha256,
                    )
                )
        return manifest_id

    def get_manifest_items(self, manifest_id: uuid.UUID) -> tuple[ManifestItem, ...]:
        """Load a manifest's frozen items (provenance for export revalidation)."""
        with self._engine.begin() as connection:
            rows = (
                connection.execute(
                    sa.select(generation_manifest_items).where(
                        generation_manifest_items.c.manifest_id == manifest_id
                    )
                )
                .mappings()
                .all()
            )
        return tuple(
            ManifestItem(
                ContentKind(row["item_kind"]), row["item_id"], row["item_sha256"]
            )
            for row in rows
        )

    def create_version(self, version: ArtifactVersionView) -> None:
        """Insert one immutable version row (the publish step; insert-only)."""
        with self._engine.begin() as connection:
            _ = connection.execute(
                sa.insert(artifact_versions).values(
                    id=version.version_id,
                    artifact_id=version.artifact_id,
                    version_number=version.version_number,
                    recipe_version=version.recipe_version,
                    recipe={"recipe_id": version.recipe_id},
                    manifest_id=version.manifest_id,
                    structured_representation=version.structured_representation,
                    rendered_blob_ids=[str(b) for b in version.rendered_blob_ids],
                    evidence_dependencies=version.evidence_dependencies,
                    composite_dependencies=version.composite_dependencies,
                    model_metadata=version.model_metadata,
                    created_by_user_id=version.created_by_user_id,
                )
            )

    def get_version(
        self, artifact_id: uuid.UUID, version_number: int
    ) -> ArtifactVersionView | None:
        """Load one version by (artifact, number); None when absent."""
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(artifact_versions).where(
                        artifact_versions.c.artifact_id == artifact_id,
                        artifact_versions.c.version_number == version_number,
                    )
                )
                .mappings()
                .one_or_none()
            )
        return _version_view(row) if row is not None else None

    def get_version_by_id(self, version_id: uuid.UUID) -> ArtifactVersionView | None:
        """Load one version by id; None when absent."""
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(artifact_versions).where(artifact_versions.c.id == version_id)
                )
                .mappings()
                .one_or_none()
            )
        return _version_view(row) if row is not None else None

    def list_versions(self, artifact_id: uuid.UUID) -> list[ArtifactVersionView]:
        """All published versions in version_number order (prior versions retained)."""
        with self._engine.begin() as connection:
            rows = (
                connection.execute(
                    sa.select(artifact_versions)
                    .where(artifact_versions.c.artifact_id == artifact_id)
                    .order_by(artifact_versions.c.version_number)
                )
                .mappings()
                .all()
            )
        return [_version_view(row) for row in rows]

    def get_user_state(
        self, user_id: uuid.UUID, artifact_version_id: uuid.UUID
    ) -> UserArtifactStateView | None:
        """Load the actor's own state row for a version; None when absent."""
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(user_artifact_state).where(
                        user_artifact_state.c.user_id == user_id,
                        user_artifact_state.c.artifact_version_id == artifact_version_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
        return _state_view(row) if row is not None else None

    def upsert_user_state(
        self,
        *,
        user_id: uuid.UUID,
        artifact_version_id: uuid.UUID,
        state: dict[str, object],
        expected_revision: int | None = None,
    ) -> UserArtifactStateView:
        """Create-or-update the actor's own row under optimistic concurrency."""
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(user_artifact_state).where(
                        user_artifact_state.c.user_id == user_id,
                        user_artifact_state.c.artifact_version_id == artifact_version_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                state_id = uuid.uuid4()
                _ = connection.execute(
                    sa.insert(user_artifact_state).values(
                        id=state_id,
                        user_id=user_id,
                        artifact_version_id=artifact_version_id,
                        state=state,
                        revision=0,
                    )
                )
                loaded = (
                    connection.execute(
                        sa.select(user_artifact_state).where(
                            user_artifact_state.c.id == state_id
                        )
                    )
                    .mappings()
                    .one()
                )
                return _state_view(loaded)
            if expected_revision is not None and int(row["revision"]) != expected_revision:
                raise ArtifactStateConflictError("study state revision conflict")
            _ = connection.execute(
                sa.update(user_artifact_state)
                .where(user_artifact_state.c.id == row["id"])
                .values(state=state, revision=user_artifact_state.c.revision + 1)
            )
            loaded = (
                connection.execute(
                    sa.select(user_artifact_state).where(
                        user_artifact_state.c.id == row["id"]
                    )
                )
                .mappings()
                .one()
            )
        return _state_view(loaded)

    def create_study_snapshot(
        self,
        *,
        user_id: uuid.UUID,
        artifact_version_id: uuid.UUID,
        source_state_id: uuid.UUID,
        snapshot: dict[str, object],
    ) -> StudySnapshotView:
        """Materialize one immutable private snapshot of the actor's state."""
        snapshot_id = uuid.uuid4()
        with self._engine.begin() as connection:
            _ = connection.execute(
                sa.insert(study_session_snapshots).values(
                    id=snapshot_id,
                    user_id=user_id,
                    artifact_version_id=artifact_version_id,
                    source_state_id=source_state_id,
                    visibility="private",
                    snapshot=snapshot,
                )
            )
            row = (
                connection.execute(
                    sa.select(study_session_snapshots).where(
                        study_session_snapshots.c.id == snapshot_id
                    )
                )
                .mappings()
                .one()
            )
        return _snapshot_view(row)


def _artifact_view(row: Any) -> ArtifactView:  # SQLAlchemy RowMapping boundary
    """Map one artifacts row onto the logical artifact view."""
    return ArtifactView(
        artifact_id=row["id"],
        notebook_id=row["notebook_id"],
        artifact_type=ArtifactType(row["artifact_type"]),
        status=ArtifactStatus(row["status"]),
        current_version_id=row["current_version_id"],
        created_by_user_id=row["created_by_user_id"],
        revision=int(row["revision"] or 0),
        etag=row["etag"] or "0",
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _version_view(row: Any) -> ArtifactVersionView:  # SQLAlchemy RowMapping boundary
    """Map one artifact_versions row onto the immutable version view."""
    return ArtifactVersionView(
        version_id=row["id"],
        artifact_id=row["artifact_id"],
        version_number=int(row["version_number"]),
        recipe_id=(row["recipe"] or {}).get("recipe_id", ""),
        recipe_version=row["recipe_version"],
        manifest_id=row["manifest_id"],
        structured_representation=row["structured_representation"],
        rendered_blob_ids=[uuid.UUID(b) for b in (row["rendered_blob_ids"] or [])],
        evidence_dependencies=row["evidence_dependencies"] or [],
        composite_dependencies=row["composite_dependencies"] or [],
        model_metadata=row["model_metadata"],
        created_by_user_id=row["created_by_user_id"],
        created_at=row["created_at"],
    )


def _state_view(row: Any) -> UserArtifactStateView:  # SQLAlchemy RowMapping boundary
    """Map one user_artifact_state row onto the per-user state view."""
    return UserArtifactStateView(
        state_id=row["id"],
        user_id=row["user_id"],
        artifact_version_id=row["artifact_version_id"],
        state=row["state"] or {},
        completed_at=row["completed_at"],
        revision=int(row["revision"] or 0),
    )


def _snapshot_view(row: Any) -> StudySnapshotView:  # SQLAlchemy RowMapping boundary
    """Map one study_session_snapshots row onto the immutable snapshot view."""
    return StudySnapshotView(
        snapshot_id=row["id"],
        user_id=row["user_id"],
        artifact_version_id=row["artifact_version_id"],
        source_state_id=row["source_state_id"],
        snapshot=row["snapshot"] or {},
        visibility=row["visibility"],
        created_at=row["created_at"],
    )
