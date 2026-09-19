"""
Row mapping for the jobs tables (FND-05): JSONB payload packing + state re-expansion.

The T3 physical schema (jobs) stores a subset of the ch15 field set as columns and the
rest inside the JSONB ``payload`` column (priority, capability, notebook, schema
version/hash, progress, checkpoint, result/error references, cancellation). This is a
prototype note, not a schema migration: the durable fields live durably in JSONB so no
new column is required. ``waiting_reason`` is the durable marker that maps the three
pending logical states onto the physical ``queued`` status.
"""

from __future__ import annotations

import uuid
from typing import Any

from milpbooklm_domain.job_events import JOB_AGGREGATE_KIND
from milpbooklm_domain.jobs import (
    REASON_STATES,
    JobProgress,
    JobRecord,
    JobState,
)

# Logical states persisted as the physical 'queued' status (marker carried in payload).
_PENDING_TO_QUEUED = {
    JobState.WAITING_CAPACITY,
    JobState.WAITING_EXTERNAL,
    JobState.RETRY_SCHEDULED,
}


def physical_status(state: JobState) -> str:
    """Map a logical state to its physical jobs.status value."""
    return "queued" if state in _PENDING_TO_QUEUED else state.value


def pack_payload(job: JobRecord) -> dict[str, object]:
    """
    Pack the full ch15 field set into the JSONB payload column.

    ``params`` is the operation's content-free parameters; the surrounding keys
    carry the durable fields the physical schema has no column for.
    """
    progress = job.progress
    return {
        "params": job.payload,
        "priority": job.priority,
        "payload_schema_version": job.payload_schema_version,
        "payload_hash": job.payload_hash_value,
        "capability": job.capability,
        "notebook_id": str(job.notebook_id) if job.notebook_id is not None else None,
        "progress": (
            {
                "phase": progress.phase,
                "fraction": progress.fraction,
                "status": progress.status,
            }
            if progress is not None
            else None
        ),
        "checkpoint": job.checkpoint,
        "result_ref": job.result_ref,
        "error_code": job.error_code,
        "waiting_reason": job.waiting_reason,
        "cancel_reason": job.cancel_reason,
    }


def unpack_logical_state(status: str, waiting_reason: str | None) -> JobState:
    """Re-expand a physical status (+ marker) to the logical state (ch15 pending states)."""
    if status == "queued" and waiting_reason is not None:
        state = REASON_STATES.get(waiting_reason)
        if state is not None:
            return state
    try:
        return JobState(status)
    except ValueError:
        return JobState.QUEUED


def job_from_row(row: Any) -> JobRecord:
    """Build the domain JobRecord from a jobs-table row (payload unpacked, state re-expanded)."""
    raw: dict[str, object] = row.payload if isinstance(row.payload, dict) else {}
    waiting_reason = raw.get("waiting_reason")
    reason: str | None = waiting_reason if isinstance(waiting_reason, str) else None
    state = unpack_logical_state(str(row.status), reason)
    progress_raw = raw.get("progress")
    progress: JobProgress | None = None
    if isinstance(progress_raw, dict):
        fraction_raw = progress_raw.get("fraction")
        status_raw = progress_raw.get("status")
        progress = JobProgress(
            phase=str(progress_raw["phase"]),
            fraction=float(fraction_raw) if fraction_raw is not None else None,
            status=str(status_raw) if status_raw is not None else None,
        )
    params_raw = raw.get("params")
    version_raw = raw.get("payload_schema_version")
    priority_raw = raw.get("priority")
    notebook_raw = raw.get("notebook_id")
    capability_raw = raw.get("capability")
    checkpoint_raw = raw.get("checkpoint")
    cancel_raw = raw.get("cancel_reason")
    result_raw = raw.get("result_ref")
    error_raw = raw.get("error_code")
    return JobRecord(
        id=row.id,
        kind=row.kind,
        queue=row.queue,
        payload=params_raw if isinstance(params_raw, dict) else {},
        payload_schema_version=version_raw if isinstance(version_raw, int) else 1,
        payload_hash_value=str(raw.get("payload_hash") or ""),
        actor_user_id=row.requested_by_user_id,
        notebook_id=uuid.UUID(str(notebook_raw)) if notebook_raw else None,
        capability=capability_raw if isinstance(capability_raw, str) else None,
        priority=priority_raw if isinstance(priority_raw, int) else 0,
        state=state,
        attempts=row.attempts,
        max_attempts=row.max_attempts,
        lease_owner=row.lease_owner,
        lease_expires_at=row.lease_expires_at,
        waiting_reason=reason,
        progress=progress,
        checkpoint=checkpoint_raw if isinstance(checkpoint_raw, dict) else None,
        result_ref=result_raw if isinstance(result_raw, str) else None,
        error_code=error_raw if isinstance(error_raw, str) else None,
        cancel_reason=cancel_raw if isinstance(cancel_raw, str) else None,
        revision=row.revision,
        enqueued_at=row.enqueued_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def aggregate_kind() -> str:
    """Return the outbox aggregate kind for job events (stable stream identity)."""
    return JOB_AGGREGATE_KIND
