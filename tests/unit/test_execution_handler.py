from __future__ import annotations

import json
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from milpbooklm_adapters.execution.outputs import OutputCollector
from milpbooklm_application.blob_store import StoredObjectStats, TemporaryStats
from milpbooklm_application.execution import (
    DeclaredOutput,
    ExecutionLimits,
    ExecutionOutcome,
    ExecutionRefusalCode,
    ExecutionRefusedError,
    ExecutionSpec,
    ExecutionStatus,
)
from milpbooklm_application.ports import AuditRetentionReport
from milpbooklm_domain.blobs import BlobObject, BlobState
from milpbooklm_domain.jobs import JobRecord
from milpbooklm_workers.execution_handler import ExecutionRunHandler


class _BlobStore:
    def __init__(self) -> None:
        self._payloads: dict[uuid.UUID, bytes] = {}

    def put(
        self,
        data: bytes | Iterable[bytes],
        *,
        content_type: str | None = None,
        referrer_kind: str | None = None,
        referrer_id: uuid.UUID | None = None,
    ) -> BlobObject:
        del referrer_kind, referrer_id
        payload = data if isinstance(data, bytes) else b"".join(data)
        blob_id = uuid.uuid4()
        self._payloads[blob_id] = payload
        return BlobObject(
            id=blob_id,
            content_sha256="a" * 64,
            size_bytes=len(payload),
            storage_path=f"objects/{blob_id}",
            state=BlobState.FINALIZED,
            content_type=content_type,
            finalized_at=datetime.now(UTC),
        )

    def get(self, blob_id: uuid.UUID) -> bytes:
        return self._payloads[blob_id]

    def verify(self, blob_id: uuid.UUID) -> None:
        self.get(blob_id)

    def verify_content(self, content_sha256: str, size_bytes: int) -> None:
        del content_sha256, size_bytes

    def list_temporaries(self) -> tuple[TemporaryStats, ...]:
        return ()

    def list_finals(self) -> tuple[StoredObjectStats, ...]:
        return ()

    def delete_temporary(self, relative_path: str) -> None:
        del relative_path

    def delete_final(self, content_sha256: str) -> None:
        del content_sha256

    @property
    def payload_count(self) -> int:
        return len(self._payloads)


class _Client:
    def __init__(self, outcome: ExecutionOutcome) -> None:
        self._outcome = outcome
        self.specs: list[ExecutionSpec] = []

    def run(self, spec: ExecutionSpec) -> ExecutionOutcome:
        self.specs.append(spec)
        return self._outcome


class _Revalidator:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed
        self.jobs: list[JobRecord] = []

    def revalidate(self, job: JobRecord) -> bool:
        self.jobs.append(job)
        return self.allowed


class _Audit:
    def __init__(self) -> None:
        self.actions: list[str] = []

    def record(
        self,
        *,
        actor_id: uuid.UUID | None,
        action: str,
        subject_kind: str | None = None,
        subject_id: uuid.UUID | None = None,
        details: dict[str, str] | None = None,
        request_id: str | None = None,
    ) -> None:
        del actor_id, subject_kind, subject_id, details, request_id
        self.actions.append(action)

    def retention_report(self, *, cutoff: datetime) -> AuditRetentionReport:
        return AuditRetentionReport(0, cutoff, None, None)


class _Context:
    def checkpoint(self, data: dict[str, object]) -> None:
        del data

    def progress(self, phase: str, fraction: float | None, status: str | None) -> None:
        del phase, fraction, status

    def should_stop(self) -> bool:
        return False


def _job() -> JobRecord:
    return JobRecord(
        id=uuid.uuid4(),
        kind="execution.run",
        queue="execution",
        payload={
            "code": "printf evidence > /workspace/outputs/result.txt",
            "declared_outputs": [{"path": "result.txt", "max_bytes": 64}],
        },
        actor_user_id=uuid.uuid4(),
        notebook_id=uuid.uuid4(),
        capability="code_data_analysis",
    )


def _outcome(collector: OutputCollector, tmp_path: Path) -> ExecutionOutcome:
    outputs_dir = tmp_path / "outputs"
    outputs_dir.mkdir()
    (outputs_dir / "result.txt").write_text("evidence")
    outputs, _undeclared = collector.collect(
        outputs_dir,
        (DeclaredOutput("result.txt", 64),),
        ExecutionLimits(),
        "handler-test",
    )
    return ExecutionOutcome(
        status=ExecutionStatus.SUCCEEDED,
        exit_code=0,
        stdout_excerpt=b"",
        stderr_excerpt=b"",
        outputs=outputs,
        wall_seconds=0.1,
        oom_kill_count=0,
        kill_method="exit",
        image_digest="sha256:" + "1" * 64,
    )


def test_handler_revalidates_durable_job_before_publishing(tmp_path: Path) -> None:
    quarantine = tmp_path / "quarantine"
    collector = OutputCollector(quarantine)
    blobs = _BlobStore()
    revalidator = _Revalidator(allowed=False)
    audit = _Audit()
    job = _job()
    code_put_count = 1
    handler = ExecutionRunHandler(
        client=_Client(_outcome(collector, tmp_path)),
        collector=collector,
        blobs=blobs,
        revalidator=revalidator,
        audit=audit,
        image_digest="sha256:" + "1" * 64,
    )

    with pytest.raises(ExecutionRefusedError) as raised:
        handler.run(job, _Context())

    assert raised.value.code is ExecutionRefusalCode.PUBLISH_AUTHZ_DENIED
    assert revalidator.jobs == [job]
    assert blobs.payload_count == code_put_count
    assert audit.actions == []
    assert tuple(quarantine.iterdir()) == ()


def test_handler_publishes_then_discards_only_quarantine(tmp_path: Path) -> None:
    quarantine = tmp_path / "quarantine"
    collector = OutputCollector(quarantine)
    blobs = _BlobStore()
    revalidator = _Revalidator(allowed=True)
    audit = _Audit()
    job = _job()
    client = _Client(_outcome(collector, tmp_path))
    handler = ExecutionRunHandler(
        client=client,
        collector=collector,
        blobs=blobs,
        revalidator=revalidator,
        audit=audit,
        image_digest="sha256:" + "1" * 64,
    )

    result = handler.run(job, _Context())
    record = json.loads(result.result_ref or "{}")
    output_blob_id = uuid.UUID(record["outputs"][0]["blob_id"])

    assert blobs.get(output_blob_id) == b"evidence"
    assert tuple(quarantine.iterdir()) == ()
    assert audit.actions == ["EXECUTION_PUBLISHED"]
    assert client.specs[0].input_blob_ids[0] == uuid.UUID(record["code_blob_id"])
