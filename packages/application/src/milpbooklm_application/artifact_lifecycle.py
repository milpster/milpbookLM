"""
Artifact lifecycle use cases (STD-01, guide/13 common lifecycle + revision).

The synchronous generation pipeline is the framework spine shared by the
initial generate, edit, and regeneration paths:

    CAS -> generating  ->  freeze manifest  ->  CAS -> validating
    ->  recipe.plan/generate/validate  ->  render renditions
    ->  publish immutable version  ->  CAS -> ready (advance current_version_id)

Every step is a compare-and-swap against the stored status; a loss surfaces as
a conflict, a recipe/validation failure moves the artifact to ``failed`` (the
published prior versions are untouched). Edits and regeneration are new
versions from a pinned base - the base's manifest is the parent of the new
manifest (lineage), and the base version itself is never mutated.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from milpbooklm_domain.artifacts import (
    ArtifactRecipe,
    ArtifactRequest,
    ArtifactStatus,
    ArtifactType,
    FrozenInputs,
    Rendition,
    artifact_transition_allowed,
)
from milpbooklm_domain.manifests import ManifestItem

from milpbooklm_application.artifact_core import (
    ArtifactCasConflictError,
    ArtifactNotFoundError,
    ArtifactNotReadyForActionError,
    ArtifactStore,
    ArtifactVersionView,
    ArtifactView,
    InvalidArtifactRequestError,
)
from milpbooklm_application.artifact_recipes import RecipeRegistry

if TYPE_CHECKING:
    from milpbooklm_application.blob_store import BlobStore


@dataclass(frozen=True, slots=True)
class GenerationResult:
    """Outcome of one generation pass: the updated artifact + the new version."""

    artifact: ArtifactView
    version: ArtifactVersionView | None
    conflict: bool
    validation_problems: tuple[str, ...] = ()


class CreateArtifact:
    """Create a logical artifact in the draft state (no generation yet)."""

    def __init__(self, store: ArtifactStore) -> None:
        """Wire the artifact store."""
        self._store = store

    def __call__(
        self,
        *,
        actor_id: uuid.UUID,
        notebook_id: uuid.UUID,
        artifact_type: ArtifactType,
        title: str,
    ) -> ArtifactView:
        """Insert the draft artifact; the actor becomes its creator."""
        now = None
        artifact = ArtifactView(
            artifact_id=uuid.uuid4(),
            notebook_id=notebook_id,
            artifact_type=artifact_type,
            status=ArtifactStatus.DRAFT,
            current_version_id=None,
            created_by_user_id=actor_id,
            revision=0,
            etag="0",
            created_at=now,
            updated_at=now,
        )
        self._store.create_artifact(artifact)
        return artifact


class _GenerationPipeline:
    """The shared freeze -> plan -> generate -> validate -> render -> publish spine."""

    def __init__(self, store: ArtifactStore, blobs: BlobStore | None) -> None:
        """Wire the artifact store and the optional blob store (renditions)."""
        self._store = store
        self._blobs = blobs

    def run(
        self,
        recipe: ArtifactRecipe,
        artifact: ArtifactView,
        request: ArtifactRequest,
        actor_id: uuid.UUID,
    ) -> tuple[ArtifactView, ArtifactVersionView]:
        """Run the pipeline; the caller has already moved the artifact to generating."""
        items = request.manifest_items()
        parent_manifest_id = self._resolve_parent(artifact.artifact_id, request)
        config_snapshot: dict[str, object] = {
            "title": request.title,
            "instructions": request.instructions,
            "recipe": recipe.recipe_id,
            "recipe_version": recipe.recipe_version,
            "base_version_number": request.base_version_number,
        }
        manifest_id = self._store.freeze_manifest(
            notebook_id=artifact.notebook_id,
            actor_id=actor_id,
            config_snapshot=config_snapshot,
            items=items,
            parent_manifest_id=parent_manifest_id,
        )
        inputs = FrozenInputs(manifest_id, items, config_snapshot)
        _ = self._store.cas_status(
            artifact.artifact_id, ArtifactStatus.GENERATING, ArtifactStatus.VALIDATING
        )
        plan = recipe.plan(request, inputs)
        content = recipe.generate(request, inputs, plan)
        problems = recipe.validate_content(content, inputs)
        if problems:
            raise ArtifactGenerationValidationError(problems)
        renditions = recipe.render(content)
        rendered_blob_ids = self._store_renditions(renditions, artifact.artifact_id)
        version = self._publish(
            artifact, recipe, manifest_id, items, content, rendered_blob_ids=rendered_blob_ids
        )
        updated = self._store.cas_status(
            artifact.artifact_id,
            ArtifactStatus.VALIDATING,
            ArtifactStatus.READY,
            field_updates={"current_version_id": version.version_id},
        )
        if updated is None:
            raise ArtifactCasConflictError("ready publication lost the CAS")
        return updated, version

    def _resolve_parent(
        self, artifact_id: uuid.UUID, request: ArtifactRequest
    ) -> uuid.UUID | None:
        """Pin the lineage: the base version's manifest is the parent manifest."""
        if request.base_version_number is None:
            return None
        base = self._store.get_version(artifact_id, request.base_version_number)
        if base is None:
            raise ArtifactNotFoundError(
                f"base version {request.base_version_number} not found"
            )
        return base.manifest_id

    def _store_renditions(
        self, renditions: tuple[Rendition, ...], artifact_id: uuid.UUID
    ) -> list[uuid.UUID]:
        """Persist renditions as separately-referenced blobs (when a store is wired)."""
        if self._blobs is None or not renditions:
            return []
        return [
            self._blobs.put(
                rendition.content,
                content_type=f"application/{rendition.format}",
                referrer_kind="artifact_version",
                referrer_id=artifact_id,
            ).id
            for rendition in renditions
        ]

    def _publish(
        self,
        artifact: ArtifactView,
        recipe: ArtifactRecipe,
        manifest_id: uuid.UUID,
        items: tuple[ManifestItem, ...],
        content: dict[str, object],
        *,
        rendered_blob_ids: list[uuid.UUID],
    ) -> ArtifactVersionView:
        """Insert the immutable version row (the publish step)."""
        version_number = _next_version_number(self._store.list_versions(artifact.artifact_id))
        evidence_dependencies: list[dict[str, object]] = [
            {"kind": item.kind.value, "id": str(item.item_id)} for item in items
        ]
        version = ArtifactVersionView(
            version_id=uuid.uuid4(),
            artifact_id=artifact.artifact_id,
            version_number=version_number,
            recipe_id=recipe.recipe_id,
            recipe_version=recipe.recipe_version,
            manifest_id=manifest_id,
            structured_representation=content,
            rendered_blob_ids=rendered_blob_ids,
            evidence_dependencies=evidence_dependencies,
            composite_dependencies=[],
            model_metadata={
                "provider_calls": [],
                "safety_status": "safe",
                "effective_restrictions": {},
                "generation_parameters": {
                    "recipe": recipe.recipe_id,
                    "recipe_version": recipe.recipe_version,
                },
            },
            created_by_user_id=artifact.created_by_user_id,
            created_at=None,
        )
        self._store.create_version(version)
        return version


class ArtifactGenerationValidationError(RuntimeError):
    """The recipe produced content that failed validation before publication."""

    def __init__(self, problems: tuple[str, ...]) -> None:
        """Carry the validation problems."""
        super().__init__("; ".join(problems))
        self.problems = problems


def _next_version_number(existing: list[ArtifactVersionView]) -> int:
    """Return the next version number: one past the highest published (kept prior)."""
    return max((version.version_number for version in existing), default=0) + 1


def _mark_failed(store: ArtifactStore, artifact_id: uuid.UUID) -> None:
    """Move the artifact to failed when a legal edge allows (terminal-safe)."""
    current = store.get_artifact(artifact_id)
    if current is not None and artifact_transition_allowed(
        current.status, ArtifactStatus.FAILED
    ):
        _ = store.cas_status(artifact_id, current.status, ArtifactStatus.FAILED)


class GenerateArtifact:
    """Initial generation: CAS draft -> generating, run the pipeline, -> ready."""

    def __init__(
        self, store: ArtifactStore, registry: RecipeRegistry, blobs: BlobStore | None
    ) -> None:
        """Wire the store, the typed recipe registry, and the optional blob store."""
        self._store = store
        self._registry = registry
        self._pipeline = _GenerationPipeline(store, blobs)

    def __call__(
        self, *, actor_id: uuid.UUID, artifact_id: uuid.UUID, request: ArtifactRequest
    ) -> GenerationResult | None:
        """Generate the first version; None when the artifact is absent."""
        artifact = self._store.get_artifact(artifact_id)
        if artifact is None:
            return None
        recipe = self._registry.get(artifact.artifact_type)
        if recipe is None:
            raise InvalidArtifactRequestError(
                f"no recipe registered for {artifact.artifact_type.value}"
            )
        recipe.validate_request(request)
        if artifact.status is not ArtifactStatus.DRAFT:
            return GenerationResult(artifact, None, conflict=True)
        updated = self._store.cas_status(
            artifact_id, ArtifactStatus.DRAFT, ArtifactStatus.GENERATING
        )
        if updated is None:
            return GenerationResult(self._store.get_artifact(artifact_id) or artifact, None, True)
        try:
            final, version = self._pipeline.run(recipe, updated, request, actor_id)
            return GenerationResult(final, version, conflict=False)
        except (ArtifactGenerationValidationError, ArtifactCasConflictError) as exc:
            _mark_failed(self._store, artifact_id)
            problems = exc.problems if isinstance(exc, ArtifactGenerationValidationError) else ()
            return GenerationResult(
                self._store.get_artifact(artifact_id) or updated, None, False, problems
            )


class EditArtifact:
    """
    Optimistic edit: a new version from the current ready version (etag CAS).

    The caller presents the artifact's etag (If-Match); a mismatch is a 409
    conflict. The edit runs the pipeline with the current version as the pinned
    base, so the new version's manifest is a child of the base's manifest.
    """

    def __init__(
        self, store: ArtifactStore, registry: RecipeRegistry, blobs: BlobStore | None
    ) -> None:
        """Wire the store, the typed recipe registry, and the optional blob store."""
        self._store = store
        self._registry = registry
        self._pipeline = _GenerationPipeline(store, blobs)

    def __call__(
        self,
        *,
        actor_id: uuid.UUID,
        artifact_id: uuid.UUID,
        expected_etag: str,
        request: ArtifactRequest,
    ) -> GenerationResult | None:
        """Create a new version under optimistic concurrency; None when absent."""
        artifact = self._store.get_artifact(artifact_id)
        if artifact is None:
            return None
        if artifact.etag != expected_etag:
            return GenerationResult(artifact, None, conflict=True)
        if artifact.status not in (ArtifactStatus.READY, ArtifactStatus.OUT_OF_DATE):
            raise ArtifactNotReadyForActionError(
                f"artifact is {artifact.status.value}; edits require a ready artifact"
            )
        recipe = self._registry.get(artifact.artifact_type)
        if recipe is None:
            raise InvalidArtifactRequestError(
                f"no recipe registered for {artifact.artifact_type.value}"
            )
        recipe.validate_request(request)
        base_number = self._current_version_number(artifact)
        request = ArtifactRequest(
            notebook_id=request.notebook_id,
            artifact_type=request.artifact_type,
            title=request.title,
            instructions=request.instructions,
            source_version_ids=request.source_version_ids,
            note_revision_ids=request.note_revision_ids,
            base_version_number=base_number,
        )
        updated = self._store.cas_status(
            artifact_id, artifact.status, ArtifactStatus.GENERATING
        )
        if updated is None:
            return GenerationResult(self._store.get_artifact(artifact_id) or artifact, None, True)
        try:
            final, version = self._pipeline.run(recipe, updated, request, actor_id)
            return GenerationResult(final, version, conflict=False)
        except (ArtifactGenerationValidationError, ArtifactCasConflictError) as exc:
            _mark_failed(self._store, artifact_id)
            problems = exc.problems if isinstance(exc, ArtifactGenerationValidationError) else ()
            return GenerationResult(
                self._store.get_artifact(artifact_id) or updated, None, False, problems
            )

    def _current_version_number(self, artifact: ArtifactView) -> int | None:
        """Return the version number the edit's new manifest should descend from."""
        if artifact.current_version_id is None:
            raise ArtifactNotReadyForActionError("artifact has no current version to edit")
        versions = self._store.list_versions(artifact.artifact_id)
        for version in versions:
            if version.version_id == artifact.current_version_id:
                return version.version_number
        return None


class RegenerateArtifact:
    """Regeneration: a new version pinned to a specific prior version's lineage."""

    def __init__(
        self, store: ArtifactStore, registry: RecipeRegistry, blobs: BlobStore | None
    ) -> None:
        """Wire the store, the typed recipe registry, and the optional blob store."""
        self._store = store
        self._registry = registry
        self._pipeline = _GenerationPipeline(store, blobs)

    def __call__(
        self,
        *,
        actor_id: uuid.UUID,
        artifact_id: uuid.UUID,
        base_version_number: int,
        request: ArtifactRequest,
    ) -> GenerationResult | None:
        """Regenerate from the pinned base; None when the artifact is absent."""
        artifact = self._store.get_artifact(artifact_id)
        if artifact is None:
            return None
        if artifact.status not in (ArtifactStatus.READY, ArtifactStatus.OUT_OF_DATE):
            raise ArtifactNotReadyForActionError(
                f"artifact is {artifact.status.value}; regeneration requires a ready artifact"
            )
        recipe = self._registry.get(artifact.artifact_type)
        if recipe is None:
            raise InvalidArtifactRequestError(
                f"no recipe registered for {artifact.artifact_type.value}"
            )
        recipe.validate_request(request)
        request = ArtifactRequest(
            notebook_id=request.notebook_id,
            artifact_type=request.artifact_type,
            title=request.title,
            instructions=request.instructions,
            source_version_ids=request.source_version_ids,
            note_revision_ids=request.note_revision_ids,
            base_version_number=base_version_number,
        )
        updated = self._store.cas_status(
            artifact_id, artifact.status, ArtifactStatus.GENERATING
        )
        if updated is None:
            return GenerationResult(self._store.get_artifact(artifact_id) or artifact, None, True)
        try:
            final, version = self._pipeline.run(recipe, updated, request, actor_id)
            return GenerationResult(final, version, conflict=False)
        except (ArtifactGenerationValidationError, ArtifactCasConflictError) as exc:
            _mark_failed(self._store, artifact_id)
            problems = exc.problems if isinstance(exc, ArtifactGenerationValidationError) else ()
            return GenerationResult(
                self._store.get_artifact(artifact_id) or updated, None, False, problems
            )


class CancelArtifact:
    """Cancel the in-flight generation pass (CAS any non-terminal -> cancelled)."""

    def __init__(self, store: ArtifactStore) -> None:
        """Wire the artifact store."""
        self._store = store

    def __call__(self, *, actor_id: uuid.UUID, artifact_id: uuid.UUID) -> ArtifactView | None:
        """Cancel; None when absent, raises when the status admits no cancel."""
        artifact = self._store.get_artifact(artifact_id)
        if artifact is None:
            return None
        if not artifact_transition_allowed(artifact.status, ArtifactStatus.CANCELLED):
            raise ArtifactNotReadyForActionError(
                f"artifact is {artifact.status.value}; cancel is not permitted"
            )
        updated = self._store.cas_status(
            artifact_id, artifact.status, ArtifactStatus.CANCELLED
        )
        if updated is None:
            raise ArtifactCasConflictError("cancel lost the CAS")
        return updated


class MarkOutOfDate:
    """Mark a ready artifact stale when a source advances (ARCH-13-010)."""

    def __init__(self, store: ArtifactStore) -> None:
        """Wire the artifact store."""
        self._store = store

    def __call__(self, *, actor_id: uuid.UUID, artifact_id: uuid.UUID) -> ArtifactView | None:
        """CAS ready -> out_of_date; None when absent, raises otherwise."""
        artifact = self._store.get_artifact(artifact_id)
        if artifact is None:
            return None
        if not artifact_transition_allowed(artifact.status, ArtifactStatus.OUT_OF_DATE):
            raise ArtifactNotReadyForActionError(
                f"artifact is {artifact.status.value}; only ready artifacts go out of date"
            )
        updated = self._store.cas_status(
            artifact_id, artifact.status, ArtifactStatus.OUT_OF_DATE
        )
        if updated is None:
            raise ArtifactCasConflictError("mark-out-of-date lost the CAS")
        return updated
