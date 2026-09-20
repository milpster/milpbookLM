"""
Blob maintenance use cases (FND-06): reconciliation classification + delayed GC.

ReconcileBlobs is a pure read: it classifies orphan temporaries, unreferenced
finalized objects and missing/corrupt referenced objects, and never deletes
anything (repeated scans are safe). CollectBlobGarbage is the separate,
intentionally invoked deletion action: it enforces the configured safety
delay - which must be strictly longer than the maximum backup-copy window
(ch21) - before any finalized object file may go away, and it never touches
missing referenced objects (those are integrity incidents, not garbage).
GC deletes files only: the FND-03 finalize-guard trigger makes the
``finalized`` row state terminal in the database, so a GC'd object's record
remains and is reported (never re-mutated) by subsequent scans.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

from milpbooklm_domain.blobs import (
    MAX_BACKUP_WINDOW,
    BlobObject,
    BlobState,
    GcReport,
    ReconciliationClass,
    ReconciliationFinding,
    ReconciliationReport,
    gc_eligible,
    gc_safety_delay_valid,
)

from milpbooklm_application.blob_store import (
    BlobIntegrityError,
    BlobRepository,
    BlobStore,
    StoredObjectStats,
)
from milpbooklm_application.ports import Clock


@dataclass(frozen=True, slots=True)
class BlobPorts:
    """The wired blob surface: ports + maintenance use cases (composition bundles it once)."""

    store: BlobStore
    repo: BlobRepository
    reconcile: ReconcileBlobs
    gc: CollectBlobGarbage


class ReconcileBlobs:
    """
    Non-destructive reconciliation scan (ch19; FND-06 micro-index 6.2).

    Classification over three artifact spaces, cross-referenced:
    temporaries on disk, finalized files on disk, and blob_objects rows plus
    their reference counts. Referenced finalized objects additionally pass an
    integrity scan (digest + size of the on-disk bytes).
    """

    def __init__(self, store: BlobStore, repo: BlobRepository, clock: Clock) -> None:
        """Wire the store, the bookkeeping repository, and the clock."""
        self._store = store
        self._repo = repo
        self._clock = clock

    def __call__(self) -> ReconciliationReport:
        """Scan and classify; reading only, so repetition is always safe."""
        findings: list[ReconciliationFinding] = list(self._classify_temporaries())
        finals = {stats.content_sha256: stats for stats in self._store.list_finals()}
        objects = self._repo.all_objects()
        ref_counts = self._repo.reference_counts()
        by_sha = {obj.content_sha256: obj for obj in objects}
        findings.extend(self._classify_finals(finals, by_sha, ref_counts))
        findings.extend(self._classify_rows(objects, finals, ref_counts))
        return ReconciliationReport(at=self._clock.now(), findings=tuple(findings))

    def _classify_temporaries(self) -> list[ReconciliationFinding]:
        """Every staged temp file is an orphan: temps never carry references."""
        return [
            ReconciliationFinding(
                kind=ReconciliationClass.ORPHAN_TEMPORARY,
                blob_id=None,
                content_sha256=None,
                storage_path=path,
                finalized_at=None,
                file_present=True,
                detail="temporary file left outside a committed write",
            )
            for path in self._store.list_temporaries()
        ]

    def _classify_finals(
        self,
        finals: Mapping[str, StoredObjectStats],
        by_sha: Mapping[str, BlobObject],
        ref_counts: Mapping[uuid.UUID, int],
    ) -> list[ReconciliationFinding]:
        """Classify each on-disk finalized file against its record and references."""
        findings: list[ReconciliationFinding] = []
        for content_sha256, stats in finals.items():
            obj = by_sha.get(content_sha256)
            if obj is None or obj.state is not BlobState.FINALIZED:
                findings.append(
                    ReconciliationFinding(
                        kind=ReconciliationClass.UNREFERENCED_FINAL,
                        blob_id=obj.id if obj is not None else None,
                        content_sha256=content_sha256,
                        storage_path=obj.storage_path if obj is not None else None,
                        finalized_at=stats.mtime,
                        file_present=True,
                        detail="finalized object on disk without a finalized record",
                    )
                )
            elif ref_counts.get(obj.id, 0) == 0:
                findings.append(
                    ReconciliationFinding(
                        kind=ReconciliationClass.UNREFERENCED_FINAL,
                        blob_id=obj.id,
                        content_sha256=content_sha256,
                        storage_path=obj.storage_path,
                        finalized_at=obj.finalized_at or stats.mtime,
                        file_present=True,
                        detail="finalized object has no references",
                    )
                )
            else:
                findings.extend(self._integrity_scan(obj))
        return findings

    def _integrity_scan(self, obj: BlobObject) -> list[ReconciliationFinding]:
        """Verify one referenced object's bytes; a failure is a missing/corrupt incident."""
        try:
            self._store.verify_content(obj.content_sha256, obj.size_bytes)
        except BlobIntegrityError as exc:
            return [
                ReconciliationFinding(
                    kind=ReconciliationClass.MISSING_REFERENCED,
                    blob_id=obj.id,
                    content_sha256=obj.content_sha256,
                    storage_path=obj.storage_path,
                    finalized_at=obj.finalized_at,
                    file_present=True,
                    detail=f"integrity scan failed: {exc}",
                )
            ]
        return []

    def _classify_rows(
        self,
        objects: list[BlobObject],
        finals: Mapping[str, StoredObjectStats],
        ref_counts: Mapping[uuid.UUID, int],
    ) -> list[ReconciliationFinding]:
        """Classify finalized records whose object file is absent from disk."""
        findings: list[ReconciliationFinding] = []
        for obj in objects:
            # staging = an in-flight write intent; purged = already GC'd.
            if obj.state is not BlobState.FINALIZED or obj.content_sha256 in finals:
                continue
            if ref_counts.get(obj.id, 0) > 0:
                findings.append(
                    ReconciliationFinding(
                        kind=ReconciliationClass.MISSING_REFERENCED,
                        blob_id=obj.id,
                        content_sha256=obj.content_sha256,
                        storage_path=obj.storage_path,
                        finalized_at=obj.finalized_at,
                        file_present=False,
                        detail="referenced blob has no object file on disk",
                    )
                )
            else:
                findings.append(
                    ReconciliationFinding(
                        kind=ReconciliationClass.UNREFERENCED_FINAL,
                        blob_id=obj.id,
                        content_sha256=obj.content_sha256,
                        storage_path=obj.storage_path,
                        finalized_at=obj.finalized_at,
                        file_present=False,
                        detail="finalized record has no object file on disk",
                    )
                )
        return findings


class CollectBlobGarbage:
    """
    Delayed physical GC (ch21; FND-06 micro-index 6.3).

    Deletion is an explicit action distinct from classification. Orphan
    temporaries are swept immediately (never referenced, never part of any
    backup); a finalized object is deleted only once its finalization is at
    least the configured safety delay old, and the delay itself must be
    strictly longer than the maximum backup-copy window (validated at
    construction, so an unsafe GC cannot even be wired). Missing referenced
    objects are never deleted - they are integrity incidents.
    """

    def __init__(
        self,
        store: BlobStore,
        repo: BlobRepository,
        clock: Clock,
        safety_delay: timedelta,
    ) -> None:
        """Wire the ports; refuse a safety delay that cannot outlive a backup window."""
        if not gc_safety_delay_valid(safety_delay):
            raise ValueError(
                "GC safety delay "
                f"{safety_delay!r} must be strictly greater than the maximum "
                f"backup-copy window {MAX_BACKUP_WINDOW!r} (ch21)"
            )
        self._store = store
        self._repo = repo
        self._clock = clock
        self._safety_delay = safety_delay

    def __call__(self) -> GcReport:
        """Run one GC pass from a fresh scan; delete only what the policy permits."""
        report = ReconcileBlobs(self._store, self._repo, self._clock)()
        now = self._clock.now()
        swept = 0
        deleted = 0
        pending = 0
        for finding in report.findings_of(ReconciliationClass.ORPHAN_TEMPORARY):
            if finding.storage_path is not None:
                self._store.delete_temporary(finding.storage_path)
                swept += 1
        for finding in report.findings_of(ReconciliationClass.UNREFERENCED_FINAL):
            if not finding.file_present:
                # Already settled: the file is gone and the record's state is
                # terminal in the DB (finalize guard) - nothing to act on.
                continue
            if self._eligible(finding, now):
                if finding.content_sha256 is not None:
                    self._store.delete_final(finding.content_sha256)
                deleted += 1
            else:
                pending += 1
        incidents = len(report.findings_of(ReconciliationClass.MISSING_REFERENCED))
        return GcReport(
            at=now,
            swept_temps=swept,
            deleted_finals=deleted,
            pending_safety_delay=pending,
            integrity_incidents=incidents,
        )

    def _eligible(self, finding: ReconciliationFinding, now: datetime) -> bool:
        """Whether the safety delay has elapsed for one unreferenced final."""
        return gc_eligible(
            finalized_at=finding.finalized_at, now=now, safety_delay=self._safety_delay
        )
