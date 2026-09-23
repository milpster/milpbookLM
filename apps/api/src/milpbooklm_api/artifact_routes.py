"""
Studio artifact routes (STD-01): lifecycle, revision, export, study state.

Every route resolves the principal, rechecks notebook authorization against the
shared policy engine, and carries the actor + request context into the use
cases and the audit trail. Generation is synchronous (the framework pipeline is
deterministic for the shipped recipe); conflicts are 409, absences 404.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Final

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from milpbooklm_application.artifact_core import (
    ArtifactNotFoundError,
    ArtifactNotReadyForActionError,
    ArtifactStateConflictError,
    ArtifactVersionView,
    ArtifactView,
    InvalidArtifactRequestError,
    StudySnapshotView,
    UserArtifactStateView,
)
from milpbooklm_application.artifact_export import ExportDeniedError, ExportGrant
from milpbooklm_application.artifact_lifecycle import GenerationResult
from milpbooklm_application.audit_actions import AuditAction
from milpbooklm_domain.artifacts import ArtifactRequest, ArtifactType
from milpbooklm_domain.policy import PolicyAction, PolicyDecision
from milpbooklm_domain.telemetry import current_context
from pydantic import BaseModel, ConfigDict, Field

from .deps import ApiDeps, ArtifactDeps, PrincipalDependency
from .security import Principal
from .source_http import authorize_notebook, problem

_HTTP_CREATED: Final = 201
_HTTP_CONFLICT: Final = 409
_HTTP_FORBIDDEN: Final = 403
_HTTP_NOT_FOUND: Final = 404

_ARTIFACT_TYPE_PATTERN: Final = (
    "^(report|table|mind_map|flashcards|quiz|slide_deck|infographic"
    "|audio_overview|video_overview|composite)$"
)


class ArtifactCreateRequest(BaseModel):
    """Logical artifact creation (draft; no generation yet)."""

    model_config = ConfigDict(frozen=True)

    notebook_id: uuid.UUID
    artifact_type: str = Field(pattern=_ARTIFACT_TYPE_PATTERN)
    title: str = Field(min_length=1, max_length=300)


class ArtifactGenerateRequest(BaseModel):
    """One generation pass: title + instructions + the exact frozen inputs."""

    model_config = ConfigDict(frozen=True)

    title: str = Field(min_length=1, max_length=300)
    instructions: str | None = Field(default=None, max_length=4_000)
    source_version_ids: tuple[uuid.UUID, ...] = ()
    note_revision_ids: tuple[uuid.UUID, ...] = ()


class ExportGrantRequest(BaseModel):
    """The request-time grant echoed back on download (the server re-derives it)."""

    model_config = ConfigDict(frozen=True)

    artifact_id: uuid.UUID
    version_number: int = Field(ge=1)
    notebook_id: uuid.UUID
    source_version_ids: tuple[uuid.UUID, ...] = ()
    requested_at: datetime | None = None


class StudyStateRequest(BaseModel):
    """The actor's own mutable study state for a version."""

    model_config = ConfigDict(frozen=True)

    state: dict[str, object]


def _request_id() -> str | None:
    """Return the correlation context's request id (None outside a request scope)."""
    context = current_context()
    return context.request_id if context is not None else None


def _artifact_payload(artifact: ArtifactView) -> dict[str, object]:
    """Serialize the logical artifact (the etag is the revision's CAS token)."""
    return {
        "artifact_id": str(artifact.artifact_id),
        "notebook_id": str(artifact.notebook_id),
        "artifact_type": artifact.artifact_type.value,
        "status": artifact.status.value,
        "current_version_id": (
            str(artifact.current_version_id) if artifact.current_version_id else None
        ),
        "revision": artifact.revision,
        "etag": artifact.etag,
        "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
        "updated_at": artifact.updated_at.isoformat() if artifact.updated_at else None,
    }


def _version_payload(version: ArtifactVersionView) -> dict[str, object]:
    """Serialize one immutable version (the canonical payload stays embedded)."""
    return {
        "version_id": str(version.version_id),
        "artifact_id": str(version.artifact_id),
        "version_number": version.version_number,
        "recipe_id": version.recipe_id,
        "recipe_version": version.recipe_version,
        "manifest_id": str(version.manifest_id),
        "structured_representation": version.structured_representation,
        "rendered_blob_ids": [str(blob_id) for blob_id in version.rendered_blob_ids],
        "evidence_dependencies": version.evidence_dependencies,
        "composite_dependencies": version.composite_dependencies,
        "model_metadata": version.model_metadata,
        "created_by_user_id": str(version.created_by_user_id),
        "created_at": version.created_at.isoformat() if version.created_at else None,
    }


def _state_payload(state: UserArtifactStateView) -> dict[str, object]:
    """Serialize one per-user study state row (the revision is the CAS token)."""
    return {
        "state_id": str(state.state_id),
        "user_id": str(state.user_id),
        "artifact_version_id": str(state.artifact_version_id),
        "state": state.state,
        "completed_at": state.completed_at.isoformat() if state.completed_at else None,
        "revision": state.revision,
    }


def _snapshot_payload(snapshot: StudySnapshotView) -> dict[str, object]:
    """Serialize one immutable private study snapshot."""
    return {
        "snapshot_id": str(snapshot.snapshot_id),
        "user_id": str(snapshot.user_id),
        "artifact_version_id": str(snapshot.artifact_version_id),
        "source_state_id": str(snapshot.source_state_id),
        "snapshot": snapshot.snapshot,
        "visibility": snapshot.visibility,
        "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
    }


def build_artifact_router(  # noqa: C901, PLR0915 - per-route handlers share one prefix
    deps: ApiDeps, principal_dependency: PrincipalDependency, artifacts: ArtifactDeps
) -> APIRouter:
    """Build the /api/v1/artifacts router over the wired use cases."""
    router = APIRouter(prefix="/api/v1/artifacts", tags=["artifacts"])

    @router.post("", status_code=_HTTP_CREATED, response_model=None)
    def create(
        body: ArtifactCreateRequest, principal: Principal = Depends(principal_dependency)
    ) -> JSONResponse:
        """Create a draft artifact in a notebook the actor may studio-generate in."""
        denied = authorize_notebook(deps, principal, body.notebook_id, PolicyAction.STUDIO_GENERATE)
        if denied is not None:
            return denied
        artifact = artifacts.create(
            actor_id=principal.user.id,
            notebook_id=body.notebook_id,
            artifact_type=ArtifactType(body.artifact_type),
            title=body.title,
        )
        deps.audit.record(
            actor_id=principal.user.id,
            action=AuditAction.ARTIFACT_CREATED.value,
            subject_kind="artifact",
            subject_id=artifact.artifact_id,
            request_id=_request_id(),
        )
        return JSONResponse(status_code=_HTTP_CREATED, content=_artifact_payload(artifact))

    @router.get("/{artifact_id}", response_model=None)
    def state(
        artifact_id: uuid.UUID, principal: Principal = Depends(principal_dependency)
    ) -> JSONResponse:
        """Return the logical artifact plus all its retained immutable versions."""
        artifact = artifacts.store.get_artifact(artifact_id)
        if artifact is None:
            return problem("artifact_not_found", "artifact not found", _HTTP_NOT_FOUND)
        denied = authorize_notebook(
            deps, principal, artifact.notebook_id, PolicyAction.READ_CONTENT
        )
        if denied is not None:
            return denied
        versions = artifacts.store.list_versions(artifact_id)
        return JSONResponse(
            content={
                **_artifact_payload(artifact),
                "versions": [_version_payload(v) for v in versions],
            }
        )

    @router.post("/{artifact_id}/generate", response_model=None)
    def generate(
        artifact_id: uuid.UUID,
        body: ArtifactGenerateRequest,
        principal: Principal = Depends(principal_dependency),
    ) -> JSONResponse:
        """Run the initial generation pass (draft -> ... -> ready) synchronously."""
        artifact = artifacts.store.get_artifact(artifact_id)
        if artifact is None:
            return problem("artifact_not_found", "artifact not found", _HTTP_NOT_FOUND)
        denied = authorize_notebook(
            deps, principal, artifact.notebook_id, PolicyAction.STUDIO_GENERATE
        )
        if denied is not None:
            return denied
        result = artifacts.generate(
            actor_id=principal.user.id,
            artifact_id=artifact_id,
            request=_to_request(artifact, body),
        )
        return _generation_response(deps, principal, result)

    @router.post("/{artifact_id}/cancel", response_model=None)
    def cancel(
        artifact_id: uuid.UUID, principal: Principal = Depends(principal_dependency)
    ) -> JSONResponse:
        """Cancel the in-flight generation pass (terminal)."""
        artifact = artifacts.store.get_artifact(artifact_id)
        if artifact is None:
            return problem("artifact_not_found", "artifact not found", _HTTP_NOT_FOUND)
        denied = authorize_notebook(
            deps, principal, artifact.notebook_id, PolicyAction.STUDIO_GENERATE
        )
        if denied is not None:
            return denied
        try:
            updated = artifacts.cancel(actor_id=principal.user.id, artifact_id=artifact_id)
        except ArtifactNotReadyForActionError as exc:
            return problem("artifact_state_conflict", str(exc), _HTTP_CONFLICT)
        if updated is None:
            return problem("artifact_not_found", "artifact not found", _HTTP_NOT_FOUND)
        return JSONResponse(content=_artifact_payload(updated))

    @router.post("/{artifact_id}/out-of-date", response_model=None)
    def mark_out_of_date(
        artifact_id: uuid.UUID, principal: Principal = Depends(principal_dependency)
    ) -> JSONResponse:
        """Mark a ready artifact stale when its sources advance (ARCH-13-010)."""
        artifact = artifacts.store.get_artifact(artifact_id)
        if artifact is None:
            return problem("artifact_not_found", "artifact not found", _HTTP_NOT_FOUND)
        denied = authorize_notebook(
            deps, principal, artifact.notebook_id, PolicyAction.STUDIO_GENERATE
        )
        if denied is not None:
            return denied
        try:
            updated = artifacts.mark_out_of_date(
                actor_id=principal.user.id, artifact_id=artifact_id
            )
        except ArtifactNotReadyForActionError as exc:
            return problem("artifact_state_conflict", str(exc), _HTTP_CONFLICT)
        if updated is None:
            return problem("artifact_not_found", "artifact not found", _HTTP_NOT_FOUND)
        return JSONResponse(content=_artifact_payload(updated))

    @router.get("/{artifact_id}/versions/{version_number}", response_model=None)
    def version(
        artifact_id: uuid.UUID,
        version_number: int,
        principal: Principal = Depends(principal_dependency),
    ) -> JSONResponse:
        """One immutable version by (artifact, number); prior versions stay readable."""
        artifact = artifacts.store.get_artifact(artifact_id)
        if artifact is None:
            return problem("artifact_not_found", "artifact not found", _HTTP_NOT_FOUND)
        denied = authorize_notebook(
            deps, principal, artifact.notebook_id, PolicyAction.READ_CONTENT
        )
        if denied is not None:
            return denied
        loaded = artifacts.store.get_version(artifact_id, version_number)
        if loaded is None:
            return problem("version_not_found", "artifact version not found", _HTTP_NOT_FOUND)
        return JSONResponse(content=_version_payload(loaded))

    @router.post("/{artifact_id}/versions", status_code=_HTTP_CREATED, response_model=None)
    def edit(
        artifact_id: uuid.UUID,
        body: ArtifactGenerateRequest,
        principal: Principal = Depends(principal_dependency),
        if_match: str = Header(alias="If-Match"),
    ) -> JSONResponse:
        """Edit: a new version from the current ready version (etag CAS -> 409)."""
        artifact = artifacts.store.get_artifact(artifact_id)
        if artifact is None:
            return problem("artifact_not_found", "artifact not found", _HTTP_NOT_FOUND)
        denied = authorize_notebook(
            deps, principal, artifact.notebook_id, PolicyAction.STUDIO_GENERATE
        )
        if denied is not None:
            return denied
        try:
            result = artifacts.edit(
                actor_id=principal.user.id,
                artifact_id=artifact_id,
                expected_etag=if_match,
                request=_to_request(artifact, body),
            )
        except (InvalidArtifactRequestError, ArtifactNotReadyForActionError) as exc:
            return problem("artifact_request_rejected", str(exc), 422)
        return _generation_response(deps, principal, result, _HTTP_CREATED)

    @router.post(
        "/{artifact_id}/versions/{version_number}/regenerate",
        status_code=_HTTP_CREATED,
        response_model=None,
    )
    def regenerate(
        artifact_id: uuid.UUID,
        version_number: int,
        body: ArtifactGenerateRequest,
        principal: Principal = Depends(principal_dependency),
    ) -> JSONResponse:
        """Regenerate: a new version pinned to a specific prior version's lineage."""
        artifact = artifacts.store.get_artifact(artifact_id)
        if artifact is None:
            return problem("artifact_not_found", "artifact not found", _HTTP_NOT_FOUND)
        denied = authorize_notebook(
            deps, principal, artifact.notebook_id, PolicyAction.STUDIO_GENERATE
        )
        if denied is not None:
            return denied
        try:
            result = artifacts.regenerate(
                actor_id=principal.user.id,
                artifact_id=artifact_id,
                base_version_number=version_number,
                request=_to_request(artifact, body),
            )
        except (InvalidArtifactRequestError, ArtifactNotReadyForActionError) as exc:
            return problem("artifact_request_rejected", str(exc), 422)
        return _generation_response(deps, principal, result, _HTTP_CREATED)

    @router.post(
        "/{artifact_id}/versions/{version_number}/export",
        response_model=None,
    )
    def export_request(
        artifact_id: uuid.UUID,
        version_number: int,
        principal: Principal = Depends(principal_dependency),
    ) -> JSONResponse:
        """Stage 1: revalidate authorization and issue the export grant."""
        artifact = artifacts.store.get_artifact(artifact_id)
        if artifact is None:
            return problem("artifact_not_found", "artifact not found", _HTTP_NOT_FOUND)
        denied = authorize_notebook(
            deps, principal, artifact.notebook_id, PolicyAction.READ_CONTENT
        )
        if denied is not None:
            return denied
        try:
            grant = artifacts.export.request(
                actor_id=principal.user.id,
                artifact_id=artifact_id,
                version_number=version_number,
            )
        except ArtifactNotFoundError:
            return problem("version_not_found", "artifact version not found", _HTTP_NOT_FOUND)
        except ExportDeniedError as exc:
            _audit_export_denied(deps, principal, artifact_id, "request", exc.decision)
            return problem(
                "export_denied", f"export denied: {exc.decision.reason.value}", _HTTP_FORBIDDEN
            )
        if grant is None:
            return problem("version_not_found", "artifact version not found", _HTTP_NOT_FOUND)
        deps.audit.record(
            actor_id=principal.user.id,
            action=AuditAction.EXPORT_INITIATED.value,
            subject_kind="artifact_version",
            subject_id=None,
            details={"artifact_id": str(artifact_id), "version_number": str(version_number)},
            request_id=_request_id(),
        )
        return JSONResponse(content=_grant_payload(grant))

    @router.post(
        "/{artifact_id}/versions/{version_number}/export/download",
        response_model=None,
    )
    def export_download(
        artifact_id: uuid.UUID,
        version_number: int,
        body: ExportGrantRequest,
        principal: Principal = Depends(principal_dependency),
    ) -> JSONResponse:
        """Stage 2: revalidate CURRENT authorization before releasing the snapshot."""
        if body.artifact_id != artifact_id or body.version_number != version_number:
            return problem("export_grant_mismatch", "grant does not match the path", 400)
        artifact = artifacts.store.get_artifact(artifact_id)
        if artifact is None:
            return problem("artifact_not_found", "artifact not found", _HTTP_NOT_FOUND)
        denied = authorize_notebook(
            deps, principal, artifact.notebook_id, PolicyAction.READ_CONTENT
        )
        if denied is not None:
            return denied
        # The server re-derives the frozen input set from the stored version row;
        # the client's echoed ids are never trusted for the restriction recheck.
        version = artifacts.store.get_version(artifact_id, version_number)
        if version is None:
            return problem("version_not_found", "artifact version not found", _HTTP_NOT_FOUND)
        source_ids = frozenset(
            uuid.UUID(str(item["id"]))
            for item in version.evidence_dependencies
            if item.get("kind") == "source_version"
        )
        grant = ExportGrant(
            artifact_id=artifact_id,
            version_number=version_number,
            notebook_id=artifact.notebook_id,
            source_version_ids=source_ids,
            requested_at=datetime.now(tz=UTC),
        )
        result = artifacts.export.download(actor_id=principal.user.id, grant=grant)
        if not result.allowed:
            _audit_export_denied(deps, principal, artifact_id, "download", result.reason)
            return problem(
                "export_denied", "export denied: restriction recheck failed", _HTTP_FORBIDDEN
            )
        return JSONResponse(
            content={"content": result.content, "version": _version_payload(version)}
        )

    @router.get("/versions/{version_id}/state", response_model=None)
    def study_state(
        version_id: uuid.UUID, principal: Principal = Depends(principal_dependency)
    ) -> JSONResponse:
        """Return the actor's own study state for a version (never another user's)."""
        denied = _authorize_version(deps, principal, version_id, PolicyAction.READ_CONTENT)
        if denied is not None:
            return denied
        state = artifacts.get_state(actor_id=principal.user.id, artifact_version_id=version_id)
        if state is None:
            return problem(
                "study_state_not_found", "no study state for this version", _HTTP_NOT_FOUND
            )
        return JSONResponse(content=_state_payload(state))

    @router.put("/versions/{version_id}/state", response_model=None)
    def update_study_state(
        version_id: uuid.UUID,
        body: StudyStateRequest,
        principal: Principal = Depends(principal_dependency),
        if_match: str | None = Header(default=None, alias="If-Match"),
    ) -> JSONResponse:
        """Create-or-update the actor's own study state (If-Match = revision CAS)."""
        denied = _authorize_version(deps, principal, version_id, PolicyAction.READ_CONTENT)
        if denied is not None:
            return denied
        try:
            expected_revision = int(if_match) if if_match is not None else None
            state = artifacts.update_state(
                actor_id=principal.user.id,
                artifact_version_id=version_id,
                state=dict(body.state),
                expected_revision=expected_revision,
            )
        except ArtifactNotFoundError:
            return problem("version_not_found", "artifact version not found", _HTTP_NOT_FOUND)
        except ArtifactStateConflictError:
            return problem("study_state_conflict", "study state revision conflict", _HTTP_CONFLICT)
        return JSONResponse(content=_state_payload(state))

    @router.post(
        "/versions/{version_id}/state/snapshot", status_code=_HTTP_CREATED, response_model=None
    )
    def snapshot_study(
        version_id: uuid.UUID, principal: Principal = Depends(principal_dependency)
    ) -> JSONResponse:
        """Freeze the actor's current study state into a private immutable snapshot."""
        denied = _authorize_version(deps, principal, version_id, PolicyAction.READ_CONTENT)
        if denied is not None:
            return denied
        try:
            snapshot = artifacts.snapshot(
                actor_id=principal.user.id, artifact_version_id=version_id
            )
        except ArtifactNotFoundError as exc:
            return problem("study_state_not_found", str(exc), _HTTP_NOT_FOUND)
        deps.audit.record(
            actor_id=principal.user.id,
            action=AuditAction.STUDY_SNAPSHOT_CREATED.value,
            subject_kind="study_snapshot",
            subject_id=snapshot.snapshot_id,
            request_id=_request_id(),
        )
        return JSONResponse(status_code=_HTTP_CREATED, content=_snapshot_payload(snapshot))

    return router


def _to_request(artifact: ArtifactView, body: ArtifactGenerateRequest) -> ArtifactRequest:
    """Build the recipe request bound to the artifact's notebook + type."""
    return ArtifactRequest(
        notebook_id=artifact.notebook_id,
        artifact_type=artifact.artifact_type,
        title=body.title,
        instructions=body.instructions,
        source_version_ids=body.source_version_ids,
        note_revision_ids=body.note_revision_ids,
    )


def _grant_payload(grant: ExportGrant) -> dict[str, object]:
    """Serialize the request-time grant (echoed back on the download call)."""
    return {
        "artifact_id": str(grant.artifact_id),
        "version_number": grant.version_number,
        "notebook_id": str(grant.notebook_id),
        "source_version_ids": sorted(str(item) for item in grant.source_version_ids),
        "requested_at": grant.requested_at.isoformat(),
    }


def _generation_response(
    deps: ApiDeps,
    principal: Principal,
    result: GenerationResult | None,
    status_code: int = 200,
) -> JSONResponse:
    """Map a GenerationResult to HTTP: 404 absent, 409 conflict, 422 failed."""
    if result is None:
        return problem("artifact_not_found", "artifact not found", _HTTP_NOT_FOUND)
    if result.conflict:
        current = result.artifact.status.value
        return problem(
            "artifact_state_conflict",
            f"artifact state conflict (current status: {current})",
            _HTTP_CONFLICT,
        )
    if result.version is None:
        problems = (
            "; ".join(result.validation_problems)
            if result.validation_problems
            else "generation failed"
        )
        return problem("artifact_generation_failed", problems, 422)
    deps.audit.record(
        actor_id=principal.user.id,
        action=AuditAction.ARTIFACT_VERSION_PUBLISHED.value,
        subject_kind="artifact_version",
        subject_id=result.version.version_id,
        details={
            "artifact_id": str(result.artifact.artifact_id),
            "version_number": str(result.version.version_number),
        },
        request_id=_request_id(),
    )
    return JSONResponse(
        status_code=status_code,
        content={
            "artifact": _artifact_payload(result.artifact),
            "version": _version_payload(result.version),
        },
    )


def _authorize_version(
    deps: ApiDeps, principal: Principal, version_id: uuid.UUID, action: PolicyAction
) -> JSONResponse | None:
    """Resolve a version to its notebook and apply the policy engine (404/403)."""
    if deps.artifacts is None:
        return problem(
            "artifacts_unavailable",
            "the artifact lifecycle is not configured for this installation",
            503,
        )
    version = deps.artifacts.store.get_version_by_id(version_id)
    if version is None:
        return problem("version_not_found", "artifact version not found", _HTTP_NOT_FOUND)
    artifact = deps.artifacts.store.get_artifact(version.artifact_id)
    if artifact is None:
        return problem("artifact_not_found", "artifact not found", _HTTP_NOT_FOUND)
    return authorize_notebook(deps, principal, artifact.notebook_id, action)


def _audit_export_denied(
    deps: ApiDeps,
    principal: Principal,
    artifact_id: uuid.UUID,
    stage: str,
    decision: object,
) -> None:
    """Record the export denial with its stable reason (the authz audit entry)."""
    reason = decision.reason.value if isinstance(decision, PolicyDecision) else "unknown"
    deps.audit.record(
        actor_id=principal.user.id,
        action=AuditAction.ARTIFACT_EXPORT_DENIED.value,
        subject_kind="artifact_version",
        subject_id=None,
        details={"artifact_id": str(artifact_id), "stage": stage, "reason": reason},
        request_id=_request_id(),
    )
