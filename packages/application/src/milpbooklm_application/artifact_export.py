"""
Artifact export with double authorization revalidation (STD-01, TECH-13-001).

An export is a renderer concern that produces a DETACHED snapshot of one exact
artifact version: once it leaves the system, application ACLs cannot revoke the
external copy (guide/13 §6). Because the snapshot is irreversible, authorization
and effective restrictions are revalidated TWICE:

* request time - the export grant is issued only if the actor may read the
  notebook and no frozen manifest input is access-restricted for them;
* download time - the grant is re-checked against CURRENT restrictions. If a
  restriction tightened between request and download, the download is denied
  and the denial is audit-logged.

The revalidation is delegated to an :class:`ExportAuthorizer` port so the use
case stays deterministic and testable; the API wires the real policy engine.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from milpbooklm_domain.policy import PolicyDecision

from milpbooklm_application.artifact_core import (
    ArtifactNotFoundError,
    ArtifactStore,
    ArtifactVersionView,
    ArtifactView,
)


class ExportAuthorizer:
    """Revalidates export authorization + effective restrictions (port)."""

    def can_export(
        self,
        *,
        actor_id: uuid.UUID,
        notebook_id: uuid.UUID,
        source_version_ids: frozenset[uuid.UUID],
    ) -> PolicyDecision:
        """Decide (membership + source restrictions) for the frozen input set."""
        raise NotImplementedError("ExportAuthorizer is a port: wire a concrete adapter")


@dataclass(frozen=True, slots=True)
class ExportGrant:
    """A request-time-authorized export of one exact version (detached snapshot)."""

    artifact_id: uuid.UUID
    version_number: int
    notebook_id: uuid.UUID
    source_version_ids: frozenset[uuid.UUID]
    requested_at: datetime


@dataclass(frozen=True, slots=True)
class ExportDownload:
    """The download-time outcome: content when allowed, the reason when denied."""

    allowed: bool
    reason: PolicyDecision | None
    content: dict[str, object] | None
    version: ArtifactVersionView | None


class ExportArtifact:
    """Two-stage export: request (grant) and download (recheck + detached bytes)."""

    def __init__(self, store: ArtifactStore, authorizer: ExportAuthorizer) -> None:
        """Wire the artifact store and the export authorizer port."""
        self._store = store
        self._authorizer = authorizer

    def request(
        self, *, actor_id: uuid.UUID, artifact_id: uuid.UUID, version_number: int
    ) -> ExportGrant | None:
        """
        Stage 1: revalidate authorization and return a grant.

        Returns None when the artifact/version is absent (404 path). Raises
        :class:`ExportDeniedError` when the actor may not export at request time.
        """
        artifact, version = self._load(artifact_id, version_number)
        source_ids = frozenset(
            uuid.UUID(str(item["id"]))
            for item in version.evidence_dependencies
            if item.get("kind") == "source_version"
        )
        decision = self._authorizer.can_export(
            actor_id=actor_id,
            notebook_id=artifact.notebook_id,
            source_version_ids=source_ids,
        )
        if not decision.allowed:
            raise ExportDeniedError(decision)
        return ExportGrant(
            artifact_id=artifact_id,
            version_number=version_number,
            notebook_id=artifact.notebook_id,
            source_version_ids=source_ids,
            requested_at=datetime.now(tz=UTC),
        )

    def download(
        self, *, actor_id: uuid.UUID, grant: ExportGrant
    ) -> ExportDownload:
        """
        Stage 2: revalidate CURRENT authorization before releasing the snapshot.

        A denial here (restriction tightened after the grant) is recorded via the
        audit port wired by the caller (the use case returns the denial; the API
        logs it). The detached content is the exact frozen version payload.
        """
        decision = self._authorizer.can_export(
            actor_id=actor_id,
            notebook_id=grant.notebook_id,
            source_version_ids=grant.source_version_ids,
        )
        if not decision.allowed:
            return ExportDownload(allowed=False, reason=decision, content=None, version=None)
        version = self._store.get_version(grant.artifact_id, grant.version_number)
        if version is None:
            raise ArtifactNotFoundError(
                f"version {grant.version_number} of {grant.artifact_id} not found"
            )
        return ExportDownload(
            allowed=True,
            reason=decision,
            content=dict(version.structured_representation or {}),
            version=version,
        )

    def _load(
        self, artifact_id: uuid.UUID, version_number: int
    ) -> tuple[ArtifactView, ArtifactVersionView]:
        """Resolve the artifact and its exact version (both must exist)."""
        artifact = self._store.get_artifact(artifact_id)
        if artifact is None:
            raise ArtifactNotFoundError(f"artifact {artifact_id} not found")
        version = self._store.get_version(artifact_id, version_number)
        if version is None:
            raise ArtifactNotFoundError(
                f"version {version_number} of {artifact_id} not found"
            )
        return artifact, version


class ExportDeniedError(RuntimeError):
    """The export was denied at request time (authorization/restriction)."""

    def __init__(self, decision: PolicyDecision) -> None:
        """Carry the authorization decision reason."""
        super().__init__(f"export denied: {decision.reason.value}")
        self.decision = decision
