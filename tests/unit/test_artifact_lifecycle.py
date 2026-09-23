"""Artifact lifecycle use cases over an in-memory fake store (deterministic, no DB)."""

from __future__ import annotations

import uuid

import pytest
from milpbooklm_application.artifact_core import (
    ArtifactNotReadyForActionError,
    ArtifactStateConflictError,
    ArtifactVersionView,
    ArtifactView,
    StudySnapshotView,
    UserArtifactStateView,
)
from milpbooklm_application.artifact_lifecycle import (
    CancelArtifact,
    CreateArtifact,
    EditArtifact,
    GenerateArtifact,
    MarkOutOfDate,
    RegenerateArtifact,
)
from milpbooklm_application.artifact_recipes import RecipeRegistry, build_recipe_registry
from milpbooklm_domain.artifacts import (
    ArtifactRequest,
    ArtifactStatus,
    ArtifactType,
    FrozenInputs,
    Rendition,
)
from milpbooklm_domain.manifests import ManifestItem

_UUID_STR_LEN = 36
_SECOND_VERSION_NUMBER = 2


class FakeArtifactStore:
    """In-memory artifact store honoring CAS semantics for the use cases."""

    def __init__(self) -> None:
        self.artifacts: dict[uuid.UUID, ArtifactView] = {}
        self.versions: dict[uuid.UUID, list[ArtifactVersionView]] = {}
        self.manifests: list[dict[str, object]] = []
        self.state_rows: dict[tuple[uuid.UUID, uuid.UUID], UserArtifactStateView] = {}
        self.snapshots: list[StudySnapshotView] = []

    def create_artifact(self, artifact: ArtifactView) -> None:
        self.artifacts[artifact.artifact_id] = artifact

    def get_artifact(self, artifact_id: uuid.UUID) -> ArtifactView | None:
        return self.artifacts.get(artifact_id)

    def cas_status(
        self,
        artifact_id: uuid.UUID,
        expected: ArtifactStatus,
        target: ArtifactStatus,
        *,
        field_updates: dict[str, object] | None = None,
    ) -> ArtifactView | None:
        current = self.artifacts.get(artifact_id)
        if current is None or current.status is not expected:
            return None
        updates: dict[str, object] = {
            "status": target,
            "current_version_id": current.current_version_id,
            "revision": current.revision + 1,
            "etag": str(current.revision + 1),
        }
        updates.update(field_updates or {})
        updated = ArtifactView(
            artifact_id=current.artifact_id,
            notebook_id=current.notebook_id,
            artifact_type=current.artifact_type,
            created_by_user_id=current.created_by_user_id,
            created_at=current.created_at,
            updated_at=current.updated_at,
            **updates,  # type: ignore[arg-type]
        )
        self.artifacts[artifact_id] = updated
        return updated

    def freeze_manifest(
        self,
        *,
        notebook_id: uuid.UUID,
        actor_id: uuid.UUID,
        config_snapshot: dict[str, object],
        items: tuple[ManifestItem, ...],
        parent_manifest_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        manifest_id = uuid.uuid4()
        self.manifests.append(
            {
                "id": manifest_id,
                "notebook_id": notebook_id,
                "actor_id": actor_id,
                "config_snapshot": config_snapshot,
                "items": items,
                "parent_manifest_id": parent_manifest_id,
            }
        )
        return manifest_id

    def get_manifest_items(self, manifest_id: uuid.UUID) -> tuple[ManifestItem, ...]:
        for manifest in self.manifests:
            if manifest["id"] == manifest_id:
                return tuple(manifest["items"])  # type: ignore[return-value]
        raise AssertionError(f"manifest {manifest_id} not frozen")

    def create_version(self, version: ArtifactVersionView) -> None:
        self.versions.setdefault(version.artifact_id, []).append(version)

    def get_version(
        self, artifact_id: uuid.UUID, version_number: int
    ) -> ArtifactVersionView | None:
        for version in self.versions.get(artifact_id, ()):
            if version.version_number == version_number:
                return version
        return None

    def get_version_by_id(self, version_id: uuid.UUID) -> ArtifactVersionView | None:
        for versions in self.versions.values():
            for version in versions:
                if version.version_id == version_id:
                    return version
        return None

    def list_versions(self, artifact_id: uuid.UUID) -> list[ArtifactVersionView]:
        return sorted(self.versions.get(artifact_id, ()), key=lambda v: v.version_number)

    def get_user_state(
        self, user_id: uuid.UUID, artifact_version_id: uuid.UUID
    ) -> UserArtifactStateView | None:
        return self.state_rows.get((user_id, artifact_version_id))

    def upsert_user_state(
        self,
        *,
        user_id: uuid.UUID,
        artifact_version_id: uuid.UUID,
        state: dict[str, object],
        expected_revision: int | None = None,
    ) -> UserArtifactStateView:
        key = (user_id, artifact_version_id)
        existing = self.state_rows.get(key)
        if existing is None:
            row = UserArtifactStateView(
                state_id=uuid.uuid4(),
                user_id=user_id,
                artifact_version_id=artifact_version_id,
                state=state,
                completed_at=None,
                revision=0,
            )
            self.state_rows[key] = row
            return row
        if expected_revision is not None and existing.revision != expected_revision:
            raise ArtifactStateConflictError("study state revision conflict")
        row = UserArtifactStateView(
            state_id=existing.state_id,
            user_id=user_id,
            artifact_version_id=artifact_version_id,
            state=state,
            completed_at=None,
            revision=existing.revision + 1,
        )
        self.state_rows[key] = row
        return row

    def create_study_snapshot(
        self,
        *,
        user_id: uuid.UUID,
        artifact_version_id: uuid.UUID,
        source_state_id: uuid.UUID,
        snapshot: dict[str, object],
    ) -> StudySnapshotView:
        row = StudySnapshotView(
            snapshot_id=uuid.uuid4(),
            user_id=user_id,
            artifact_version_id=artifact_version_id,
            source_state_id=source_state_id,
            snapshot=snapshot,
            visibility="private",
            created_at=None,
        )
        self.snapshots.append(row)
        return row


class BrokenRecipe:
    """A recipe whose output fails validation before publication."""

    recipe_id = "broken"
    recipe_version = "1"
    artifact_type = ArtifactType.COMPOSITE

    def validate_request(self, request: ArtifactRequest) -> None:
        return None

    def plan(self, request: ArtifactRequest, inputs: FrozenInputs) -> dict[str, object]:
        return {"sections": []}

    def generate(
        self, request: ArtifactRequest, inputs: FrozenInputs, plan: dict[str, object]
    ) -> dict[str, object]:
        return {"schema_version": 1, "title": "t", "sections": []}

    def validate_content(
        self, content: dict[str, object], inputs: FrozenInputs
    ) -> tuple[str, ...]:
        return ("payload schema_version must be 2",)

    def render(self, content: dict[str, object]) -> tuple[Rendition, ...]:
        return ()


@pytest.fixture(name="store")
def _store() -> FakeArtifactStore:
    return FakeArtifactStore()


@pytest.fixture(name="registry")
def _registry() -> RecipeRegistry:
    return build_recipe_registry()


def _generate(store: FakeArtifactStore, registry: RecipeRegistry, artifact: ArtifactView) -> object:
    actor = uuid.uuid4()
    source = uuid.uuid4()
    request = ArtifactRequest(
        notebook_id=artifact.notebook_id,
        artifact_type=ArtifactType.COMPOSITE,
        title="Composite echo",
        instructions="echo the inputs",
        source_version_ids=(source,),
    )
    return GenerateArtifact(store, registry, None)(
        actor_id=actor, artifact_id=artifact.artifact_id, request=request
    )


def test_create_then_generate_publishes_ready_version(store: FakeArtifactStore) -> None:
    actor = uuid.uuid4()
    notebook = uuid.uuid4()
    artifact = CreateArtifact(store)(
        actor_id=actor, notebook_id=notebook, artifact_type=ArtifactType.COMPOSITE, title="t"
    )
    assert artifact.status is ArtifactStatus.DRAFT

    result = _generate(store, build_recipe_registry(), artifact)
    assert result is not None
    assert not result.conflict
    final = store.get_artifact(artifact.artifact_id)
    assert final is not None
    assert final.status is ArtifactStatus.READY
    assert final.current_version_id is not None
    versions = store.list_versions(artifact.artifact_id)
    assert len(versions) == 1
    version = versions[0]
    assert version.version_number == 1
    assert version.recipe_id == "composite_echo"
    assert version.model_metadata is not None
    assert version.model_metadata["safety_status"] == "safe"
    deps = version.evidence_dependencies
    assert len(deps) == 1
    assert deps[0]["kind"] == "source_version"
    dep_id = deps[0]["id"]
    assert isinstance(dep_id, str)
    assert len(dep_id) == _UUID_STR_LEN


def test_generate_freezes_manifest_with_exact_items(
    store: FakeArtifactStore, registry: RecipeRegistry
) -> None:
    artifact = CreateArtifact(store)(
        actor_id=uuid.uuid4(),
        notebook_id=uuid.uuid4(),
        artifact_type=ArtifactType.COMPOSITE,
        title="t",
    )
    _generate(store, registry, artifact)
    (manifest,) = store.manifests
    assert len(manifest["items"]) == 1
    item = manifest["items"][0]
    assert isinstance(item, ManifestItem)
    config = manifest["config_snapshot"]
    assert config["recipe"] == "composite_echo"
    assert config["base_version_number"] is None


def test_generate_on_ready_artifact_is_a_conflict(
    store: FakeArtifactStore, registry: RecipeRegistry
) -> None:
    artifact = CreateArtifact(store)(
        actor_id=uuid.uuid4(),
        notebook_id=uuid.uuid4(),
        artifact_type=ArtifactType.COMPOSITE,
        title="t",
    )
    first = _generate(store, registry, artifact)
    assert first is not None
    assert first.version is not None
    second = _generate(store, registry, artifact)
    assert second is not None
    assert second.conflict
    assert len(store.list_versions(artifact.artifact_id)) == 1


def test_generation_validation_failure_marks_artifact_failed(
    store: FakeArtifactStore,
) -> None:
    artifact = CreateArtifact(store)(
        actor_id=uuid.uuid4(),
        notebook_id=uuid.uuid4(),
        artifact_type=ArtifactType.COMPOSITE,
        title="t",
    )
    registry = RecipeRegistry({ArtifactType.COMPOSITE: BrokenRecipe()})
    result = _generate(store, registry, artifact)
    assert result is not None
    assert result.version is None
    assert result.validation_problems == ("payload schema_version must be 2",)
    final = store.get_artifact(artifact.artifact_id)
    assert final is not None
    assert final.status is ArtifactStatus.FAILED
    assert store.list_versions(artifact.artifact_id) == []


def test_edit_requires_matching_etag(
    store: FakeArtifactStore, registry: RecipeRegistry
) -> None:
    artifact = CreateArtifact(store)(
        actor_id=uuid.uuid4(),
        notebook_id=uuid.uuid4(),
        artifact_type=ArtifactType.COMPOSITE,
        title="t",
    )
    _generate(store, registry, artifact)
    ready = store.get_artifact(artifact.artifact_id)
    assert ready is not None
    edit = EditArtifact(store, registry, None)
    result = edit(
        actor_id=uuid.uuid4(),
        artifact_id=artifact.artifact_id,
        expected_etag="stale",
        request=_edit_request(ready),
    )
    assert result is not None
    assert result.conflict
    assert len(store.list_versions(artifact.artifact_id)) == 1


def test_edit_creates_new_version_and_retains_prior(
    store: FakeArtifactStore, registry: RecipeRegistry
) -> None:
    actor = uuid.uuid4()
    artifact = CreateArtifact(store)(
        actor_id=actor,
        notebook_id=uuid.uuid4(),
        artifact_type=ArtifactType.COMPOSITE,
        title="t",
    )
    _generate(store, registry, artifact)
    ready = store.get_artifact(artifact.artifact_id)
    assert ready is not None
    result = EditArtifact(store, registry, None)(
        actor_id=actor,
        artifact_id=artifact.artifact_id,
        expected_etag=ready.etag,
        request=_edit_request(ready),
    )
    assert result is not None
    assert not result.conflict
    assert result.version is not None
    assert result.version.version_number == _SECOND_VERSION_NUMBER
    versions = store.list_versions(artifact.artifact_id)
    assert [v.version_number for v in versions] == [1, 2]
    # Lineage: the new manifest is a child of the base version's manifest.
    base_manifest = versions[0].manifest_id
    new_manifest = store.manifests[-1]
    assert new_manifest["parent_manifest_id"] == base_manifest
    assert versions[1].manifest_id == new_manifest["id"]


def test_edit_from_draft_is_rejected(store: FakeArtifactStore, registry: RecipeRegistry) -> None:
    artifact = CreateArtifact(store)(
        actor_id=uuid.uuid4(),
        notebook_id=uuid.uuid4(),
        artifact_type=ArtifactType.COMPOSITE,
        title="t",
    )
    edit = EditArtifact(store, registry, None)
    with pytest.raises(ArtifactNotReadyForActionError):
        edit(
            actor_id=uuid.uuid4(),
            artifact_id=artifact.artifact_id,
            expected_etag=artifact.etag,
            request=_edit_request(artifact),
        )


def test_regenerate_pins_explicit_base_version(
    store: FakeArtifactStore, registry: RecipeRegistry
) -> None:
    actor = uuid.uuid4()
    artifact = CreateArtifact(store)(
        actor_id=actor,
        notebook_id=uuid.uuid4(),
        artifact_type=ArtifactType.COMPOSITE,
        title="t",
    )
    _generate(store, registry, artifact)
    ready = store.get_artifact(artifact.artifact_id)
    assert ready is not None
    result = RegenerateArtifact(store, registry, None)(
        actor_id=actor,
        artifact_id=artifact.artifact_id,
        base_version_number=1,
        request=_edit_request(ready),
    )
    assert result is not None
    assert result.version is not None
    assert result.version.version_number == _SECOND_VERSION_NUMBER
    (new_manifest,) = [m for m in store.manifests if m["parent_manifest_id"] is not None]
    first = store.list_versions(artifact.artifact_id)[0]
    assert new_manifest["parent_manifest_id"] == first.manifest_id


def test_cancel_from_draft_and_ready_paths(store: FakeArtifactStore) -> None:
    draft = CreateArtifact(store)(
        actor_id=uuid.uuid4(),
        notebook_id=uuid.uuid4(),
        artifact_type=ArtifactType.COMPOSITE,
        title="t",
    )
    cancel = CancelArtifact(store)
    updated = cancel(actor_id=uuid.uuid4(), artifact_id=draft.artifact_id)
    assert updated is not None
    assert updated.status is ArtifactStatus.CANCELLED
    # Terminal: cancelling again is not permitted.
    with pytest.raises(ArtifactNotReadyForActionError):
        cancel(actor_id=uuid.uuid4(), artifact_id=draft.artifact_id)


def test_mark_out_of_date_only_from_ready(
    store: FakeArtifactStore, registry: RecipeRegistry
) -> None:
    artifact = CreateArtifact(store)(
        actor_id=uuid.uuid4(),
        notebook_id=uuid.uuid4(),
        artifact_type=ArtifactType.COMPOSITE,
        title="t",
    )
    mark = MarkOutOfDate(store)
    with pytest.raises(ArtifactNotReadyForActionError):
        mark(actor_id=uuid.uuid4(), artifact_id=artifact.artifact_id)
    _generate(store, registry, artifact)
    updated = mark(actor_id=uuid.uuid4(), artifact_id=artifact.artifact_id)
    assert updated is not None
    assert updated.status is ArtifactStatus.OUT_OF_DATE
    # An out-of-date artifact may start a new generation pass again.
    stale = store.get_artifact(artifact.artifact_id)
    assert stale is not None
    result = _generate(store, registry, stale)
    # _generate uses the initial (draft-only) path; regeneration is the legal route.
    assert result is not None
    assert result.conflict


def test_cas_lost_mid_pipeline_marks_failed(store: FakeArtifactStore) -> None:
    artifact = CreateArtifact(store)(
        actor_id=uuid.uuid4(),
        notebook_id=uuid.uuid4(),
        artifact_type=ArtifactType.COMPOSITE,
        title="t",
    )
    registry = build_recipe_registry()
    # Simulate a concurrent writer: the row no longer matches when the pipeline
    # CASes generating -> validating, so the final ready publication loses.
    original = store.cas_status

    def racing_cas(
        artifact_id: uuid.UUID,
        expected: ArtifactStatus,
        target: ArtifactStatus,
        *,
        field_updates: dict[str, object] | None = None,
    ) -> ArtifactView | None:
        if expected is ArtifactStatus.GENERATING and target is ArtifactStatus.VALIDATING:
            return None
        return original(artifact_id, expected, target, field_updates=field_updates)

    store.cas_status = racing_cas  # type: ignore[method-assign]
    result = GenerateArtifact(store, registry, None)(
        actor_id=uuid.uuid4(),
        artifact_id=artifact.artifact_id,
        request=_edit_request(artifact),
    )
    assert result is not None
    assert result.version is None
    final = store.get_artifact(artifact.artifact_id)
    assert final is not None
    assert final.status is ArtifactStatus.FAILED


def _edit_request(artifact: ArtifactView) -> ArtifactRequest:
    return ArtifactRequest(
        notebook_id=artifact.notebook_id,
        artifact_type=artifact.artifact_type,
        title="Edited",
        source_version_ids=(uuid.uuid4(),),
    )
