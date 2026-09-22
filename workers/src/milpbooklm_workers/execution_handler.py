"""
Durable execution job wiring for EXE-01.

The path is job -> broker -> sandbox -> validated outputs -> publication with provenance.

``execution.run`` is the code_data_analysis job kind: the handler stages the
requested code as a content-addressed blob, signs one execution spec, sends it
through the REAL Unix-socket broker (SO_PEERCRED + Ed25519 envelope + nonce
guard), and only after the sandbox reports success does it publish the
collected outputs through the blob protocol with per-output authorization
revalidation (AD-021) and job-referenced provenance. Non-success terminal
states (failed/OOM/timeout/policy violation) fail the job honestly with
metadata-only errors - stdout/stderr content never enters durable job rows
(arch ch12 §9: traces are user-private).
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from milpbooklm_adapters.execution import (
    BrokerExecutionClient,
    BubblewrapExecutionProvider,
    ExecutionBroker,
    OutputCollector,
    RuntimeImageStore,
    generate_signing_keypair,
    probe_execution_host,
)
from milpbooklm_application.blob_store import BlobStore
from milpbooklm_application.execution import (
    DeclaredOutput,
    ExecutionLimits,
    ExecutionOutcome,
    ExecutionProvider,
    ExecutionSpec,
    ExecutionStatus,
)
from milpbooklm_application.job_ports import AuthzRevalidator
from milpbooklm_application.ports import AuditLog
from milpbooklm_domain.jobs import JobRecord

from milpbooklm_workers.handlers import JobContext, JobResult

MAX_INPUT_BLOBS: Final = 4
MAX_DECLARED_OUTPUTS: Final = 8
MAX_CODE_BYTES: Final = 64 * 1024
DEFAULT_WALL_TIMEOUT_SECONDS: Final = 20.0
MAX_WALL_TIMEOUT_SECONDS: Final = 30.0
_CODE_MEDIA_TYPE: Final = "text/x-shellscript"
# argv[0..1] are the busybox runtime image contract (/bin symlinks to usr/bin);
# the staged code blob is always the first read-only input file.
_SHELL_ARGV: Final = ("/bin/busybox", "sh", "/workspace/inputs/input-000.bin")


class ExecutionRunFailedError(RuntimeError):
    """The sandbox reported a non-success terminal state (metadata only)."""

    def __init__(self, status: ExecutionStatus, outcome: ExecutionOutcome) -> None:
        """Bind the typed terminal state without any stream content."""
        super().__init__(
            f"execution terminated as {status.value}: exit={outcome.exit_code} "
            f"oom_kills={outcome.oom_kill_count} kill={outcome.kill_method}"
        )
        self.status = status


class ExecutionPayloadError(RuntimeError):
    """The durable payload did not parse (typed, content-free)."""


class _BlobInputReader:
    """The broker's narrow read service over finalized blobs (nothing else)."""

    def __init__(self, blobs: BlobStore) -> None:
        """Bind the blob store."""
        self._blobs = blobs

    def read(self, blob_id: uuid.UUID) -> bytes:
        """Return one finalized blob's bytes (integrity-verified by the store)."""
        return self._blobs.get(blob_id)


class ExecutionRunHandler:
    """The ``execution.run`` job kind: one broker-supervised sandbox execution."""

    kind = "execution.run"

    def __init__(
        self,
        *,
        client: ExecutionProvider,
        collector: OutputCollector,
        blobs: BlobStore,
        revalidator: AuthzRevalidator,
        audit: AuditLog,
        image_digest: str,
    ) -> None:
        """Wire the broker client, the shared collector, blobs, authz and audit."""
        self._client = client
        self._collector = collector
        self._blobs = blobs
        self._revalidator = revalidator
        self._audit = audit
        self._image_digest = image_digest

    def run(self, job: JobRecord, context: JobContext) -> JobResult:
        """Stage code, execute through the broker, publish validated outputs."""
        del context  # the broker supervises the whole execution; no checkpoints
        actor_id, notebook_id = _job_scope(job)
        code = _payload_code(job)
        input_blob_ids = _payload_input_blobs(job)
        declared = _payload_declared_outputs(job)
        timeout = _payload_timeout(job)
        code_blob = self._blobs.put(
            code.encode("utf-8"),
            content_type=_CODE_MEDIA_TYPE,
            referrer_kind="execution_input",
            referrer_id=job.id,
        )
        data_args = tuple(
            f"/workspace/inputs/input-{index:03d}.bin"
            for index in range(1, len(input_blob_ids) + 1)
        )
        spec = ExecutionSpec(
            image_digest=self._image_digest,
            argv=_SHELL_ARGV + data_args,
            input_blob_ids=(code_blob.id, *input_blob_ids),
            declared_outputs=declared,
            limits=ExecutionLimits(wall_timeout_seconds=timeout),
        )
        outcome = self._client.run(spec)
        if outcome.status is not ExecutionStatus.SUCCEEDED:
            raise ExecutionRunFailedError(outcome.status, outcome)
        try:
            published = self._collector.publish(
                outcome.outputs,
                authorize=lambda _output: self._revalidator.revalidate(job),
                blobs=self._blobs,
                referrer_kind="execution_run",
                referrer_id=job.id,
            )
        finally:
            self._collector.discard(outcome.outputs)
        self._audit.record(
            actor_id=actor_id,
            action="EXECUTION_PUBLISHED",
            subject_kind="notebook",
            subject_id=notebook_id,
            details={
                "job_id": str(job.id),
                "outputs": str(len(published)),
                "image_digest": self._image_digest,
            },
        )
        record = {
            "status": outcome.status.value,
            "exit_code": outcome.exit_code,
            "wall_seconds": round(outcome.wall_seconds, 3),
            "oom_kill_count": outcome.oom_kill_count,
            "kill_method": outcome.kill_method,
            "truncated_streams": outcome.truncated_streams,
            "image_digest": self._image_digest,
            "code_blob_id": str(code_blob.id),
            "input_blob_ids": [str(blob_id) for blob_id in input_blob_ids],
            "notebook_id": str(notebook_id),
            "actor_user_id": str(actor_id),
            "outputs": [
                {
                    "declared_path": output.declared_path,
                    "content_sha256": output.content_sha256,
                    "size_bytes": output.size_bytes,
                    "sniffed_media": output.sniffed_media,
                    "blob_id": str(output.blob_id) if output.blob_id else None,
                }
                for output in published
            ],
        }
        return JobResult(result_ref=json.dumps(record, sort_keys=True))

@dataclass(frozen=True)
class ExecutionStack:
    """The worker-process execution deployment: broker thread + client + handler."""

    handler: ExecutionRunHandler
    broker: ExecutionBroker

    def close(self) -> None:
        """Close the listening broker socket (the daemon thread then exits)."""
        self.broker.close()


def open_execution_stack(
    *,
    root: Path,
    runtime_image: Path,
    image_name: str,
    blobs: BlobStore,
    revalidator: AuthzRevalidator,
    audit: AuditLog,
) -> ExecutionStack:
    """
    Probe the host fail-closed, install the runtime image, and serve the broker.

    The broker runs as a daemon thread inside the worker process (the recorded
    prototype deployment form: the user-space core under the current account;
    the dedicated-account systemd form stays the T8-class deferral). Serving
    is sequential - one execution at a time IS the concurrency limit.
    """
    posture = probe_execution_host()
    if not posture.execution_available:
        notes = "; ".join(posture.notes) or "host prerequisites unsatisfied"
        raise SystemExit(f"error: execution host posture unavailable: {notes}")
    images = RuntimeImageStore(root / "images")
    digest = images.install(
        runtime_image, name=image_name, sbom={"packages": [image_name]}
    )
    collector = OutputCollector(root / "quarantine")
    provider = BubblewrapExecutionProvider(
        posture=posture,
        images=images,
        read_service=_BlobInputReader(blobs),
        work_root=root / "work",
        collector=collector,
    )
    socket_path = root / "broker.sock"
    secret_key, public_key = generate_signing_keypair()
    broker = ExecutionBroker(
        socket_path,
        provider=provider,
        public_key=public_key,
        allowed_uids=frozenset({os.getuid()}),
    )
    broker.listen()
    threading.Thread(target=broker.serve, name="execution-broker", daemon=True).start()
    client = BrokerExecutionClient(socket_path, secret_key=secret_key)
    handler = ExecutionRunHandler(
        client=client,
        collector=collector,
        blobs=blobs,
        revalidator=revalidator,
        audit=audit,
        image_digest=digest,
    )
    return ExecutionStack(handler=handler, broker=broker)


def _job_scope(job: JobRecord) -> tuple[uuid.UUID, uuid.UUID]:
    if job.actor_user_id is None:
        raise ExecutionPayloadError("missing_actor_user_id")
    if job.notebook_id is None:
        raise ExecutionPayloadError("missing_notebook_id")
    for key, expected in (
        ("actor_user_id", job.actor_user_id),
        ("notebook_id", job.notebook_id),
    ):
        supplied = job.payload.get(key)
        if supplied is not None and supplied != str(expected):
            raise ExecutionPayloadError(f"mismatched_{key}")
    return job.actor_user_id, job.notebook_id


def _payload_uuid(job: JobRecord, key: str) -> uuid.UUID:
    value = job.payload.get(key)
    if not isinstance(value, str):
        raise ExecutionPayloadError(f"missing_{key}")
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ExecutionPayloadError(f"invalid_{key}") from exc


def _payload_code(job: JobRecord) -> str:
    code = job.payload.get("code")
    if not isinstance(code, str) or not code:
        raise ExecutionPayloadError("missing_code")
    if len(code.encode("utf-8")) > MAX_CODE_BYTES:
        raise ExecutionPayloadError("code_too_large")
    return code


def _payload_input_blobs(job: JobRecord) -> tuple[uuid.UUID, ...]:
    raw = job.payload.get("input_blob_ids", [])
    if not isinstance(raw, list) or len(raw) > MAX_INPUT_BLOBS:
        raise ExecutionPayloadError("invalid_input_blob_ids")
    blob_ids = tuple(_uuid_or_fail(entry, "input_blob_ids") for entry in raw)
    if len(set(blob_ids)) != len(blob_ids):
        raise ExecutionPayloadError("duplicate_input_blob_ids")
    return blob_ids


def _payload_declared_outputs(job: JobRecord) -> tuple[DeclaredOutput, ...]:
    raw = job.payload.get("declared_outputs", [])
    if not isinstance(raw, list) or len(raw) > MAX_DECLARED_OUTPUTS:
        raise ExecutionPayloadError("invalid_declared_outputs")
    declared: list[DeclaredOutput] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ExecutionPayloadError("invalid_declared_output")
        path = entry.get("path")
        max_bytes = entry.get("max_bytes")
        if not isinstance(path, str) or not isinstance(max_bytes, int):
            raise ExecutionPayloadError("invalid_declared_output")
        cap = ExecutionLimits().max_output_file_bytes
        if not 0 < max_bytes <= cap:
            raise ExecutionPayloadError("declared_output_cap_out_of_range")
        declared.append(DeclaredOutput(relative_path=path, max_bytes=max_bytes))
    return tuple(declared)


def _payload_timeout(job: JobRecord) -> float:
    raw = job.payload.get("wall_timeout_seconds", DEFAULT_WALL_TIMEOUT_SECONDS)
    if not isinstance(raw, (int, float)):
        raise ExecutionPayloadError("invalid_wall_timeout_seconds")
    timeout = float(raw)
    if not 0 < timeout <= MAX_WALL_TIMEOUT_SECONDS:
        raise ExecutionPayloadError("wall_timeout_out_of_range")
    return timeout


def _uuid_or_fail(value: object, field: str) -> uuid.UUID:
    if not isinstance(value, str):
        raise ExecutionPayloadError(f"invalid_{field}")
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ExecutionPayloadError(f"invalid_{field}") from exc
