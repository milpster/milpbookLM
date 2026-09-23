"""Two-stage export: the download revalidates authorization, not just the grant."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from milpbooklm_application.artifact_core import (
    ArtifactNotFoundError,
    ArtifactVersionView,
    ArtifactView,
)
from milpbooklm_application.artifact_export import (
    ExportArtifact,
    ExportDeniedError,
    ExportGrant,
)
from milpbooklm_domain.artifacts import ArtifactStatus, ArtifactType
from milpbooklm_domain.policy import PolicyDecision, PolicyReason


class FakeExportStore:
    """A store carrying one artifact with one published version."""

    def __init__(self, artifact: ArtifactView, version: ArtifactVersionView) -> None:
        self.artifact = artifact
        self.version = version

    def get_artifact(self, artifact_id: uuid.UUID) -> ArtifactView | None:
        return self.artifact if artifact_id == self.artifact.artifact_id else None

    def get_version(
        self, artifact_id: uuid.UUID, version_number: int
    ) -> ArtifactVersionView | None:
        if (
            artifact_id == self.artifact.artifact_id
            and version_number == self.version.version_number
        ):
            return self.version
        return None


class FlippingAuthorizer:
    """ExportAuthorizer port impl whose decision the test can tighten at runtime."""

    def __init__(self, decision: PolicyDecision) -> None:
        self.decision = decision
        self.seen: frozenset[uuid.UUID] = frozenset()

    def can_export(
        self,
        *,
        actor_id: uuid.UUID,
        notebook_id: uuid.UUID,
        source_version_ids: frozenset[uuid.UUID],
    ) -> PolicyDecision:
        self.seen = source_version_ids
        return self.decision


@dataclass(frozen=True, slots=True)
class _Scenario:
    store: FakeExportStore
    authorizer: FlippingAuthorizer
    export: ExportArtifact
    artifact_id: uuid.UUID


def _scenario() -> _Scenario:
    artifact_id = uuid.uuid4()
    version_id = uuid.uuid4()
    source_a = uuid.uuid4()
    note_rev = uuid.uuid4()
    artifact = ArtifactView(
        artifact_id=artifact_id,
        notebook_id=uuid.uuid4(),
        artifact_type=ArtifactType.COMPOSITE,
        status=ArtifactStatus.READY,
        current_version_id=version_id,
        created_by_user_id=uuid.uuid4(),
        revision=1,
        etag="1",
        created_at=None,
        updated_at=None,
    )
    version = ArtifactVersionView(
        version_id=version_id,
        artifact_id=artifact_id,
        version_number=1,
        recipe_id="composite_echo",
        recipe_version="1.0.0",
        manifest_id=uuid.uuid4(),
        structured_representation={"schema_version": 2, "title": "t", "sections": []},
        rendered_blob_ids=[],
        evidence_dependencies=[
            {"kind": "source_version", "id": str(source_a)},
            {"kind": "note_revision", "id": str(note_rev)},
        ],
        composite_dependencies=[],
        model_metadata=None,
        created_by_user_id=artifact.created_by_user_id,
        created_at=None,
    )
    store = FakeExportStore(artifact, version)
    authorizer = FlippingAuthorizer(PolicyDecision(True, PolicyReason.ALLOW_MATRIX))
    return _Scenario(store, authorizer, ExportArtifact(store, authorizer), artifact_id)


def test_request_derives_source_ids_from_evidence_dependencies_only() -> None:
    scenario = _scenario()
    grant = scenario.export.request(
        actor_id=uuid.uuid4(), artifact_id=scenario.artifact_id, version_number=1
    )
    assert grant is not None
    # Only source_version-kind dependencies feed the restriction recheck.
    assert len(scenario.authorizer.seen) == 1
    assert grant.source_version_ids == scenario.authorizer.seen


def test_request_denial_raises_with_reason() -> None:
    scenario = _scenario()
    scenario.authorizer.decision = PolicyDecision(False, PolicyReason.DENY_SOURCE_RESTRICTION)
    with pytest.raises(ExportDeniedError) as exc:
        scenario.export.request(
            actor_id=uuid.uuid4(), artifact_id=scenario.artifact_id, version_number=1
        )
    assert exc.value.decision.reason is PolicyReason.DENY_SOURCE_RESTRICTION


def test_download_revalidates_and_denies_after_tightening() -> None:
    scenario = _scenario()
    actor = uuid.uuid4()
    grant = scenario.export.request(
        actor_id=actor, artifact_id=scenario.artifact_id, version_number=1
    )
    assert grant is not None
    # The restriction tightens between the grant and the download.
    scenario.authorizer.decision = PolicyDecision(False, PolicyReason.DENY_SOURCE_RESTRICTION)
    result = scenario.export.download(actor_id=actor, grant=grant)
    assert not result.allowed
    assert result.reason is not None
    assert result.reason.reason is PolicyReason.DENY_SOURCE_RESTRICTION
    assert result.content is None
    assert result.version is None


def test_download_allowed_returns_the_exact_frozen_payload() -> None:
    scenario = _scenario()
    actor = uuid.uuid4()
    grant = scenario.export.request(
        actor_id=actor, artifact_id=scenario.artifact_id, version_number=1
    )
    assert grant is not None
    result = scenario.export.download(actor_id=actor, grant=grant)
    assert result.allowed
    assert result.version is not None
    assert result.version.version_id == scenario.store.version.version_id
    assert result.content == scenario.store.version.structured_representation


def test_download_of_absent_version_raises_not_found() -> None:
    scenario = _scenario()
    actor = uuid.uuid4()
    grant = ExportGrant(
        artifact_id=scenario.artifact_id,
        version_number=99,
        notebook_id=scenario.store.artifact.notebook_id,
        source_version_ids=frozenset(),
        requested_at=datetime.now(tz=UTC),
    )
    with pytest.raises(ArtifactNotFoundError):
        scenario.export.download(actor_id=actor, grant=grant)
