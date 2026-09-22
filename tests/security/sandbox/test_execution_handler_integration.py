from __future__ import annotations

import json
import shutil
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from milpbooklm_application.blob_store import StoredObjectStats, TemporaryStats
from milpbooklm_application.ports import AuditRetentionReport
from milpbooklm_domain.blobs import BlobObject, BlobState
from milpbooklm_domain.jobs import JobRecord
from milpbooklm_workers.execution_handler import open_execution_stack


class _BlobStore:
    def __init__(self) -> None:
        self.payloads: dict[uuid.UUID, bytes] = {}

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
        self.payloads[blob_id] = payload
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
        return self.payloads[blob_id]

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


class _Revalidator:
    def revalidate(self, job: JobRecord) -> bool:
        return job.actor_user_id is not None and job.notebook_id is not None


class _Audit:
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
        del actor_id, action, subject_kind, subject_id, details, request_id

    def retention_report(self, *, cutoff: datetime) -> AuditRetentionReport:
        return AuditRetentionReport(0, cutoff, None, None)


class _Context:
    def checkpoint(self, data: dict[str, object]) -> None:
        del data

    def progress(self, phase: str, fraction: float | None, status: str | None) -> None:
        del phase, fraction, status

    def should_stop(self) -> bool:
        return False


def test_execution_job_reaches_real_bwrap_and_publishes_validated_output(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime" / "usr" / "bin"
    runtime.mkdir(parents=True)
    shutil.copy2("/usr/bin/busybox", runtime / "busybox")
    blobs = _BlobStore()
    stack = open_execution_stack(
        root=tmp_path / "execution",
        runtime_image=runtime.parents[1],
        image_name="busybox-test",
        blobs=blobs,
        revalidator=_Revalidator(),
        audit=_Audit(),
    )
    job = JobRecord(
        id=uuid.uuid4(),
        kind="execution.run",
        queue="execution",
        payload={
            "code": "printf gate-proof > /workspace/outputs/result.txt",
            "declared_outputs": [{"path": "result.txt", "max_bytes": 64}],
        },
        actor_user_id=uuid.uuid4(),
        notebook_id=uuid.uuid4(),
        capability="code_data_analysis",
    )
    try:
        result = stack.handler.run(job, _Context())
    finally:
        stack.close()

    record = json.loads(result.result_ref or "{}")
    output_id = uuid.UUID(record["outputs"][0]["blob_id"])
    assert record["status"] == "succeeded"
    assert blobs.get(output_id) == b"gate-proof"
    assert tuple((tmp_path / "execution" / "quarantine").iterdir()) == ()
