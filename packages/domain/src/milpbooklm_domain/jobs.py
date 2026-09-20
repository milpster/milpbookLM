"""
Durable job state machine (ch15, FND-05).

Jobs carry everything a long-running operation needs to be safe across worker
crashes: type, versioned+hashed payload, initiating actor, notebook, capability,
priority, attempts, lease owner/expiry, scoped idempotency key, cancellation,
progress/checkpoint and result/error references. Every transition goes through
``apply_transition``, which enforces the compare-and-swap state table: a
transition is legal only from its exact expected state, so a stale worker can
never move a job it no longer owns.

The three pending states (``waiting_external``, ``waiting_capacity``,
``retry_scheduled``) are explicit, durable job states - "generate later" is a
job with a visible reason, never an in-memory timer. Adapters that store only
the six physical database states map the pending ones onto ``queued`` plus a
durable ``waiting_reason`` marker and re-expand them on read.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, fields, replace
from datetime import UTC, datetime
from enum import StrEnum


class JobState(StrEnum):
    """Durable job states (ch15: queued -> running -> succeeded|failed|cancelled)."""

    QUEUED = "queued"
    LEASED = "leased"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    WAITING_EXTERNAL = "waiting_external"
    WAITING_CAPACITY = "waiting_capacity"
    RETRY_SCHEDULED = "retry_scheduled"


TERMINAL_STATES: frozenset[JobState] = frozenset(
    {JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED}
)

PENDING_STATES: frozenset[JobState] = frozenset(
    {JobState.WAITING_EXTERNAL, JobState.WAITING_CAPACITY, JobState.RETRY_SCHEDULED}
)

# Durable waiting_reason markers (payload column) for the three pending states.
WAITING_REASONS: dict[JobState, str] = {
    JobState.WAITING_CAPACITY: "capacity",
    JobState.WAITING_EXTERNAL: "external",
    JobState.RETRY_SCHEDULED: "retry_scheduled",
}
REASON_STATES: dict[str, JobState] = {reason: state for state, reason in WAITING_REASONS.items()}

# The compare-and-swap transition table: state -> states it may legally become.
_TRANSITIONS: dict[JobState, frozenset[JobState]] = {
    JobState.QUEUED: frozenset(
        {
            JobState.LEASED,
            JobState.CANCELLED,
            JobState.WAITING_CAPACITY,
            JobState.WAITING_EXTERNAL,
            JobState.RETRY_SCHEDULED,
        }
    ),
    JobState.LEASED: frozenset(
        {JobState.RUNNING, JobState.QUEUED, JobState.CANCELLED, JobState.FAILED}
    ),
    JobState.RUNNING: frozenset(
        {
            JobState.SUCCEEDED,
            JobState.FAILED,
            JobState.CANCELLED,
            # Lease expiry on a running job re-queues it for a safe retry (idempotent
            # handlers only, ch15); the reaper decides re-queue vs failed by attempts.
            JobState.QUEUED,
            JobState.WAITING_EXTERNAL,
            JobState.WAITING_CAPACITY,
            JobState.RETRY_SCHEDULED,
        }
    ),
    # Pending states are resumable: capacity frees / external work reconciles / the
    # retry window elapses, or the user cancels the durable deferral.
    JobState.WAITING_EXTERNAL: frozenset(
        {JobState.RUNNING, JobState.QUEUED, JobState.CANCELLED, JobState.FAILED}
    ),
    JobState.WAITING_CAPACITY: frozenset({JobState.QUEUED, JobState.CANCELLED}),
    JobState.RETRY_SCHEDULED: frozenset({JobState.QUEUED, JobState.CANCELLED}),
    JobState.SUCCEEDED: frozenset(),
    JobState.FAILED: frozenset(),
    JobState.CANCELLED: frozenset(),
}


class IllegalJobTransitionError(ValueError):
    """A state transition outside the CAS table (stale worker, double-terminal, ...)."""


@dataclass(frozen=True, slots=True)
class JobProgress:
    """User-visible progress (ARCH-15-001: phase, measurable fraction, status text)."""

    phase: str
    fraction: float | None = None
    status: str | None = None


class CapacityClass(StrEnum):
    """The five durable capacity classes (ch15 "Fairness and authorization")."""

    INTERACTIVE_TEXT = "interactive_text"
    INGESTION_INDEXING = "ingestion_indexing"
    RESEARCH_BROWSER = "research_browser"
    EXECUTION = "execution"
    MEDIA = "media"


def payload_hash(kind: str, payload: dict[str, object], schema_version: int) -> str:
    """Canonical SHA-256 over (kind, schema version, payload) - the idempotency identity."""
    canonical = json.dumps(
        {"kind": kind, "schema_version": schema_version, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class JobRecord:
    """
    One durable job (the full ch15 field set).

    ``payload`` is the operation's minimal parameters (content-free discipline:
    large/sensitive material crosses by authorized resource reference, never
    copied in). ``result_ref``/``error_code`` are references, not payloads.
    """

    id: uuid.UUID
    kind: str
    queue: str  # capacity class value (CapacityClass)
    payload: dict[str, object]
    payload_schema_version: int = 1
    payload_hash_value: str = ""
    actor_user_id: uuid.UUID | None = None
    request_id: str | None = None
    trace_id: str | None = None
    notebook_id: uuid.UUID | None = None
    capability: str | None = None
    priority: int = 0
    state: JobState = JobState.QUEUED
    attempts: int = 0
    max_attempts: int = 3
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    idempotency_scope: str | None = None
    idempotency_key: str | None = None
    cancelled_at: datetime | None = None
    cancel_reason: str | None = None
    progress: JobProgress | None = None
    checkpoint: dict[str, object] | None = None
    result_ref: str | None = None
    error_code: str | None = None
    waiting_reason: str | None = None
    revision: int = 0
    enqueued_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def terminal(self) -> bool:
        """True when no further transition is possible."""
        return self.state in TERMINAL_STATES


def apply_transition(job: JobRecord, new_state: JobState, **field_updates: object) -> JobRecord:
    """
    Return the job moved to ``new_state`` (immutable CAS transition).

    Raises :class:`IllegalJobTransitionError` when the move is not in the transition
    table for the job's CURRENT state - the compare-and-swap guard. ``field_updates``
    carries the transition's side data (lease owner, cancellation reason, ...).
    """
    if new_state not in _TRANSITIONS[job.state]:
        raise IllegalJobTransitionError(
            f"{job.state.value} -> {new_state.value} is not a legal transition"
        )
    known = {f.name for f in fields(JobRecord)}
    unknown = set(field_updates) - known
    if unknown:
        raise IllegalJobTransitionError(f"unknown transition field(s): {sorted(unknown)}")
    updated: dict[str, object] = dict(field_updates)
    updated["state"] = new_state
    updated["revision"] = job.revision + 1
    if new_state in TERMINAL_STATES and job.finished_at is None:
        updated.setdefault("finished_at", datetime.now(tz=UTC))
    if new_state in PENDING_STATES:
        updated["waiting_reason"] = WAITING_REASONS[new_state]
    elif new_state not in PENDING_STATES:
        updated["waiting_reason"] = None
    if new_state is JobState.CANCELLED:
        updated.setdefault("cancelled_at", datetime.now(tz=UTC))
    # The field names were validated against JobRecord above; the value types are
    # set by the callers from domain values, so the dict[str, object] unpack is sound.
    return replace(job, **updated)  # type: ignore[arg-type]
