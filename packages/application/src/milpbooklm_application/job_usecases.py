"""
Job lifecycle use cases (FND-05): enqueue, cancel, complete, lease recovery.

The use cases own the policy decisions (idempotency scoping, capacity budget
checks, terminal event envelopes); the repository port owns the atomic
persistence (one transaction per mutation, terminal + outbox committed
together). Actors cross as T4's InitiatingActor (the job acts as the user who
initiated it, never as a service account).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from milpbooklm_domain.job_capacity import CapacityPolicy, capacity_saturated
from milpbooklm_domain.job_events import (
    EVENT_JOB_CANCELLED,
    EVENT_JOB_FAILED,
    EVENT_JOB_SUCCEEDED,
    EventEnvelope,
    job_event_payload,
)
from milpbooklm_domain.jobs import (
    CapacityClass,
    JobRecord,
    JobState,
    apply_transition,
    payload_hash,
)

from milpbooklm_application.job_actor import InitiatingActor
from milpbooklm_application.job_ports import (
    AuthzRevalidator,
    JobNotFoundError,
    JobRepository,
    OutboxDispatcher,
)

ENQUEUE_PAYLOAD_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class JobPorts:
    """The wired job surface: ports + lifecycle use cases (composition bundles it once)."""

    repo: JobRepository
    dispatcher: OutboxDispatcher
    enqueue: EnqueueJob
    cancel: CancelJob
    complete: CompleteJob
    recover: RecoverExpiredLeases


def idempotency_scope(actor: InitiatingActor, kind: str, notebook_id: uuid.UUID | None) -> str:
    """
    Build the idempotency key scope: principal + command + resource boundary (ch15).

    The same user issuing the same command against the same resource reuses a
    key; a different user or resource never collides with it.
    """
    resource = str(notebook_id) if notebook_id is not None else "*"
    return f"job:{kind}:{actor.user_id}:{resource}"


class EnqueueJob:
    """
    Enqueue durable work (the 202 path): idempotency-checked, budget-checked.

    When the job's class is saturated at enqueue time the job is durably parked
    as ``waiting_capacity`` (visible reason, cancellable) - never an in-memory
    timer (ch15 MUST NOT).
    """

    def __init__(self, repo: JobRepository, policy: CapacityPolicy) -> None:
        """Wire the repository port and the capacity policy."""
        self._repo = repo
        self._policy = policy

    def __call__(
        self,
        *,
        kind: str,
        payload: dict[str, object],
        actor: InitiatingActor,
        capacity_class: CapacityClass,
        priority: int = 0,
        notebook_id: uuid.UUID | None = None,
        capability: str | None = None,
        idempotency_key: str | None = None,
        max_attempts: int = 3,
    ) -> tuple[JobRecord, bool]:
        """
        Enqueue the job and return (job, created).

        IdempotencyConflictError on key reuse with a materially different
        request (the API maps it to 409).
        """
        request_hash = payload_hash(kind, payload, ENQUEUE_PAYLOAD_SCHEMA_VERSION)
        scope = idempotency_scope(actor, kind, notebook_id) if idempotency_key is not None else None
        job = self._with_capacity_check(
            kind=kind,
            payload=payload,
            actor=actor,
            capacity_class=capacity_class,
            priority=priority,
            notebook_id=notebook_id,
            capability=capability,
            max_attempts=max_attempts,
        )
        return self._repo.enqueue(
            job,
            request_hash=request_hash,
            idempotency_scope=scope,
            idempotency_key=idempotency_key,
        )

    def _with_capacity_check(
        self,
        *,
        kind: str,
        payload: dict[str, object],
        actor: InitiatingActor,
        capacity_class: CapacityClass,
        priority: int,
        notebook_id: uuid.UUID | None,
        capability: str | None,
        max_attempts: int,
    ) -> JobRecord:
        """Build the job; park it durably when its class budget is saturated (enqueue check)."""
        job = JobRecord(
            id=uuid.uuid4(),
            kind=kind,
            queue=capacity_class.value,
            payload=payload,
            payload_schema_version=ENQUEUE_PAYLOAD_SCHEMA_VERSION,
            payload_hash_value=payload_hash(kind, payload, ENQUEUE_PAYLOAD_SCHEMA_VERSION),
            actor_user_id=actor.user_id,
            request_id=actor.request_id,
            notebook_id=notebook_id,
            capability=capability,
            priority=priority,
            state=JobState.QUEUED,
            max_attempts=max_attempts,
        )
        budget = self._policy.budget(capacity_class)
        saturated = capacity_saturated(
            budget,
            in_flight_class=self._repo.in_flight(capacity_class.value),
            in_flight_user=self._repo.in_flight_for_user(
                capacity_class.value, actor.user_id
            ),
        )
        if saturated:
            job = apply_transition(job, JobState.WAITING_CAPACITY)
        return job


class CancelJob:
    """User cancellation: a command against the durable job, not a TCP side effect (ch15)."""

    def __init__(self, repo: JobRepository) -> None:
        """Wire the repository port."""
        self._repo = repo

    def __call__(self, job_id: uuid.UUID, *, reason: str = "user_requested") -> JobRecord:
        """Cancel the job durably (terminal event published in the same transaction)."""
        job = self._repo.get(job_id)
        if job is None:
            raise JobNotFoundError(str(job_id))
        payload = job_event_payload(job)
        payload["cancel_reason"] = reason
        envelope = EventEnvelope(
            event_id=uuid.uuid4(),
            event_type=EVENT_JOB_CANCELLED,
            aggregate_kind="job",
            aggregate_id=job.id,
            aggregate_version=job.revision,
            occurred_at=job.updated_at or datetime.now(tz=UTC),
            payload=payload,
            actor_id=job.actor_user_id,
            operation_id=job.request_id,
            job_id=job.id,
        )
        return self._repo.cancel(job, reason=reason, envelope=envelope)


class CompleteJob:
    """
    Terminal publication (worker path): CAS to succeeded/failed.

    The terminal event commits atomically with the state (ch15).
    """

    def __init__(self, repo: JobRepository, revalidator: AuthzRevalidator | None = None) -> None:
        """Wire the repository port and the (optional) authorization revalidator."""
        self._repo = repo
        self._revalidator = revalidator

    def __call__(
        self,
        job: JobRecord,
        *,
        succeeded: bool,
        result_ref: str | None = None,
        error_code: str | None = None,
    ) -> JobRecord:
        """Publish the terminal state + event in one transaction; JobCasConflictError when lost."""
        if self._revalidator is not None and not self._revalidator.revalidate(job):
            return CancelJob(self._repo)(job.id, reason="authorization_revoked")
        new_state = JobState.SUCCEEDED if succeeded else JobState.FAILED
        event_type = EVENT_JOB_SUCCEEDED if succeeded else EVENT_JOB_FAILED
        final = apply_transition(job, new_state, result_ref=result_ref, error_code=error_code)
        envelope = EventEnvelope(
            event_id=uuid.uuid4(),
            event_type=event_type,
            aggregate_kind="job",
            aggregate_id=job.id,
            aggregate_version=job.revision,
            occurred_at=datetime.now(tz=UTC),
            payload=job_event_payload(final),
            actor_id=job.actor_user_id,
            operation_id=job.request_id,
            job_id=job.id,
        )
        return self._repo.complete(
            job, new_state, result_ref=result_ref, error_code=error_code, envelope=envelope
        )


class RecoverExpiredLeases:
    """The scheduler's orphan reaper (ARCH-15-014): detect, expire, re-queue or fail."""

    def __init__(self, repo: JobRepository) -> None:
        """Wire the repository port."""
        self._repo = repo

    def __call__(self) -> list[JobRecord]:
        """Reap expired leases; return the jobs whose state changed."""
        return self._repo.recover_expired()
