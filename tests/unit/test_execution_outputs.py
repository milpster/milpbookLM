from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from milpbooklm_adapters.execution.outputs import OutputCollector
from milpbooklm_application.execution import (
    DeclaredOutput,
    ExecutionLimits,
    ExecutionRefusalCode,
    ExecutionRefusedError,
)
from milpbooklm_domain.blobs import BlobObject, BlobState


class _RecordingBlobStore:
    def __init__(self) -> None:
        self.puts: list[bytes] = []

    def put(
        self,
        data: bytes | Iterable[bytes],
        *,
        content_type: str | None = None,
        referrer_kind: str | None = None,
        referrer_id: uuid.UUID | None = None,
    ) -> BlobObject:
        payload = data if isinstance(data, bytes) else b"".join(data)
        self.puts.append(payload)
        return BlobObject(
            id=uuid.uuid4(),
            content_sha256="a" * 64,
            size_bytes=len(payload),
            storage_path="objects/a",
            state=BlobState.FINALIZED,
            content_type=content_type,
            finalized_at=datetime.now(UTC),
        )


def test_declared_output_is_quarantined_then_published_after_authorization(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    (outputs / "result.txt").write_text("safe result")
    collector = OutputCollector(tmp_path / "quarantine")

    collected, undeclared = collector.collect(
        outputs,
        (DeclaredOutput("result.txt", 64),),
        ExecutionLimits(),
        "run-1",
    )
    blobs = _RecordingBlobStore()
    published = collector.publish(
        collected,
        authorize=lambda _output: True,
        blobs=blobs,
        referrer_kind="execution",
        referrer_id=uuid.uuid4(),
    )

    assert undeclared == 0
    assert collected[0].declared_path == "result.txt"
    assert Path(collected[0].quarantine_path).read_bytes() == b"safe result"
    assert blobs.puts == [b"safe result"]
    assert published[0].blob_id is not None


def test_undeclared_output_is_rejected(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    (outputs / "declared.txt").write_text("declared")
    (outputs / "secret.txt").write_text("must not escape")

    with pytest.raises(ExecutionRefusedError) as raised:
        OutputCollector(tmp_path / "quarantine").collect(
            outputs,
            (DeclaredOutput("declared.txt", 64),),
            ExecutionLimits(),
            "run-2",
        )

    assert raised.value.code is ExecutionRefusalCode.OUTPUT_POLICY_VIOLATION


def test_symlink_output_is_rejected(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("host data")
    (outputs / "result.txt").symlink_to(outside)

    with pytest.raises(ExecutionRefusedError):
        OutputCollector(tmp_path / "quarantine").collect(
            outputs,
            (DeclaredOutput("result.txt", 64),),
            ExecutionLimits(),
            "run-3",
        )


def test_authorization_denial_precedes_blob_write(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    (outputs / "result.txt").write_text("safe result")
    collector = OutputCollector(tmp_path / "quarantine")
    collected, _undeclared = collector.collect(
        outputs,
        (DeclaredOutput("result.txt", 64),),
        ExecutionLimits(),
        "run-4",
    )
    blobs = _RecordingBlobStore()

    with pytest.raises(ExecutionRefusedError) as raised:
        collector.publish(
            collected,
            authorize=lambda _output: False,
            blobs=blobs,
            referrer_kind="execution",
            referrer_id=uuid.uuid4(),
        )

    assert raised.value.code is ExecutionRefusalCode.PUBLISH_AUTHZ_DENIED
    assert blobs.puts == []


def test_discard_rejects_forged_quarantine_identity(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    (outputs / "result.txt").write_text("safe result")
    collector = OutputCollector(tmp_path / "quarantine")
    collected, _undeclared = collector.collect(
        outputs,
        (DeclaredOutput("result.txt", 64),),
        ExecutionLimits(),
        "run-5",
    )
    outside = tmp_path / "outside" / "keep.txt"
    outside.parent.mkdir()
    outside.write_text("keep")

    with pytest.raises(ExecutionRefusedError):
        collector.discard((replace(collected[0], quarantine_path=str(outside)),))

    assert outside.read_text() == "keep"


def test_empty_output_collection_creates_no_quarantine_directory(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    quarantine = tmp_path / "quarantine"
    collector = OutputCollector(quarantine)

    collected, undeclared = collector.collect(outputs, (), ExecutionLimits(), "run-empty")
    collector.discard(collected)

    assert collected == ()
    assert undeclared == 0
    assert tuple(quarantine.iterdir()) == ()
