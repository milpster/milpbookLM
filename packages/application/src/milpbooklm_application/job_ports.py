"""
Job ports (application-layer contracts; adapters implement them, FND-05).

No framework types cross these ports: the PostgreSQL adapter translates the
jobs/job_attempts/outbox_events/idempotency_keys tables (T3 schema) into the
pure domain JobRecord and EventEnvelope. Terminal publication and the outbox
commit happen in ONE transaction inside the adapter (ch15: "terminal
publication and outbox event commit atomically").
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from milpbooklm_domain.job_capacity import CapacityPolicy
from milpbooklm_domain.job_events import EventEnvelope
from milpbooklm_domain.jobs import JobProgress, JobRecord, JobState


class JobNotFoundError(LookupError):
    """The targeted job is unknown to the repository."""


class IdempotencyConflictError(ValueError):
    """A scoped idempotency key was reused with a materially different request (409)."""


class JobCasConflictError(RuntimeError):
    """A compare-and-swap transition lost: the job moved under a concurrent writer."""


@dataclass(frozen=True, slots=True)
class OutboxEvent:
    """One dispatched/visible outbox row: the stream sequence plus the envelope dict."""

    seq: int
    event_id: uuid.UUID
    event_type: str
    aggregate_id: uuid.UUID
    occurred_at: datetime
    envelope: dict[str, object]


class JobRepository(Protocol):
    """
    Durable job persistence + leasing (ch15).

    State mapping note: the three pending domain states persist as physical
    ``queued`` rows carrying a durable ``waiting_reason`` marker; the adapter
    re-expands them on read, so CAS transitions see the logical states.
    """

    def enqueue(
        self,
        job: JobRecord,
        *,
        request_hash: str,
        idempotency_scope: str | None = None,
        idempotency_key: str | None = None,
    ) -> tuple[JobRecord, bool]:
        """
        Persist a new job (with its idempotency key claim) in one transaction.

        Returns (job, created). created=False means a same-scope/same-key/same-hash
        duplicate returned the existing job (no double-run). A same-key different-
        hash reuse raises :class:`IdempotencyConflictError`.
        """
        ...

    def get(self, job_id: uuid.UUID) -> JobRecord | None:
        """Return the job (logical states re-expanded), or None."""
        ...

    def claim(
        self,
        *,
        worker_id: str,
        capacity_class: str,
        lease_seconds: int,
        policy: CapacityPolicy,
        handled_kinds: Sequence[str],
    ) -> JobRecord | None:
        """
        Claim one queued handled job of the class (FOR UPDATE SKIP LOCKED, bounded lease).

        Enforces the class + per-user concurrency budgets; returns None when the
        class is saturated or has no queued work (the work stays durably queued).
        """
        ...

    def heartbeat(self, job_id: uuid.UUID, worker_id: str, *, lease_seconds: int) -> bool:
        """Extend the lease of a job this worker owns; False when the lease is gone."""
        ...

    def record_progress(
        self,
        job: JobRecord,
        *,
        progress: JobProgress | None = None,
        checkpoint: dict[str, object] | None = None,
        lease_seconds: int,
    ) -> JobRecord | None:
        """
        Persist progress and/or a durable checkpoint and extend the lease in one write.

        ``progress``/``checkpoint`` of None keep the current value. Returns the
        updated job, or None when the lease is gone (the job was re-queued / taken
        by a reaper), in which case the worker must stop cooperatively.
        """
        ...

    def transition(
        self, job: JobRecord, new_state: JobState, **field_updates: object
    ) -> JobRecord:
        """CAS a non-terminal transition (raises JobCasConflictError when lost)."""
        ...

    def complete(
        self,
        job: JobRecord,
        new_state: JobState,
        *,
        result_ref: str | None = None,
        error_code: str | None = None,
        envelope: EventEnvelope,
    ) -> JobRecord:
        """
        CAS to a terminal state and publish the terminal event in the SAME transaction.

        At-least-once downstream: the outbox row is the single source of the event.
        """
        ...

    def cancel(self, job: JobRecord, *, reason: str, envelope: EventEnvelope) -> JobRecord:
        """CAS to cancelled (from any non-terminal state) with the event in the same tx."""
        ...

    def recover_expired(self) -> list[JobRecord]:
        """
        Reap jobs whose lease expired: re-queue (attempts left) or fail + publish.

        Only safe for idempotent/resumable handlers (ch15); the reaper itself is
        CAS-guarded, so a slow original worker that wakes up loses the race.
        """
        ...

    def running_jobs(self, capacity_class: str) -> list[JobRecord]:
        """List leased+running jobs of the class, oldest first (preemption targets)."""
        ...

    def in_flight(self, capacity_class: str) -> int:
        """Count leased+running jobs of the class (installation-wide)."""
        ...

    def in_flight_for_user(self, capacity_class: str, user_id: uuid.UUID) -> int:
        """Count leased+running jobs of the class for one user."""
        ...


class OutboxDispatcher(Protocol):
    """
    Outbox read side: monotonic per-stream sequences + delivery marking (ch15).

    The global outbox identity is monotonic; every stream (all job events, or one
    job's events) sees a monotonic subsequence. SSE clients resume with the last
    sequence they saw (Last-Event-ID); gaps trigger resource resynchronization.
    """

    def stream_job_events(self, after_seq: int, *, limit: int = 100) -> list[OutboxEvent]:
        """Return job events with seq > after_seq, in sequence order."""
        ...

    def job_events_since(
        self, job_id: uuid.UUID, after_seq: int, *, limit: int = 100
    ) -> list[OutboxEvent]:
        """Return ONE job's events (its per-job stream) with seq > after_seq."""
        ...

    def max_job_event_seq(self) -> int:
        """Return the highest job-event stream sequence (0 when none)."""
        ...

    def mark_dispatched(self, seqs: list[int]) -> None:
        """Mark outbox rows as delivered (idempotent; at-least-once delivery)."""
        ...


class AuthzRevalidator(Protocol):
    """
    Revalidate the initiating actor's CURRENT permission (ch15 / AD-021).

    Runs before dispatch and before final publication: accepting a job does not
    freeze authorization forever.
    """

    def revalidate(self, job: JobRecord) -> bool:
        """Return True when the actor may (still) run this job's capability right now."""
        ...
