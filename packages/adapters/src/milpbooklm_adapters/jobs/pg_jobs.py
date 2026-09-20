"""
PostgreSQL job repository (ch15, FND-05).

Claiming uses ``FOR UPDATE SKIP LOCKED`` so many workers poll the same queue without
blockers; leases are bounded and heartbeatable. State transitions are compare-and-swap
(``WHERE status=:expected AND revision=:expected``), so a stale worker can never move a
job it no longer owns. Terminal publication commits atomically with its outbox event
(``append_outbox`` joins the caller's transaction). Idempotency is the scoped unique
``(scope, key)`` with the request hash as the conflict discriminator: a same-key
different-hash reuse raises (409), a same-key same-hash reuse returns the existing job.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from milpbooklm_application.job_ports import (
    IdempotencyConflictError,
    JobCasConflictError,
)
from milpbooklm_domain.job_capacity import CapacityPolicy
from milpbooklm_domain.job_events import (
    EVENT_JOB_FAILED,
    EventEnvelope,
    job_event_payload,
)
from milpbooklm_domain.jobs import (
    PENDING_STATES,
    CapacityClass,
    JobProgress,
    JobRecord,
    JobState,
    apply_transition,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert

from milpbooklm_adapters.db.tables.ops import idempotency_keys, job_attempts, jobs
from milpbooklm_adapters.jobs._rows import job_from_row, pack_payload, physical_status
from milpbooklm_adapters.jobs.pg_outbox import append_outbox

_IDEMPOTENCY_TTL_SECONDS = 86400
_CLAIM_BATCH = 50


class PgJobRepository:
    """The jobs/job_attempts tables adapter implementing the JobRepository port."""

    def __init__(self, engine: sa.engine.Engine) -> None:
        """Wire the engine."""
        self._engine = engine

    def enqueue(
        self,
        job: JobRecord,
        *,
        request_hash: str,
        idempotency_scope: str | None = None,
        idempotency_key: str | None = None,
    ) -> tuple[JobRecord, bool]:
        """Persist the job (and its idempotency claim) atomically; return (job, created)."""
        with self._engine.begin() as conn:
            key_id = self._claim_idempotency(
                conn, job, request_hash, idempotency_scope, idempotency_key
            )
            if key_id is not None:
                existing = self._job_for_key(conn, key_id)
                if existing is not None:
                    return existing, False
            row = self._insert_job(conn, job, key_id)
            return job_from_row(row), True

    def _claim_idempotency(
        self,
        conn: sa.engine.Connection,
        job: JobRecord,
        request_hash: str,
        scope: str | None,
        key: str | None,
    ) -> uuid.UUID | None:
        """Claim the scoped key; return the key id (or None when the job is keyless)."""
        if scope is None or key is None:
            return None
        inserted = conn.execute(
            pg_insert(idempotency_keys)
            .values(
                scope=scope,
                key=key,
                request_hash=request_hash,
                expires_at=datetime.now(tz=UTC) + timedelta(seconds=_IDEMPOTENCY_TTL_SECONDS),
            )
            .on_conflict_do_nothing(index_elements=["scope", "key"])
            .returning(idempotency_keys.c.id)
        ).first()
        if inserted is not None:
            return self._uuid(inserted[0])
        existing = conn.execute(
            sa.select(idempotency_keys.c.id, idempotency_keys.c.request_hash).where(
                idempotency_keys.c.scope == scope, idempotency_keys.c.key == key
            )
        ).one()
        if existing[1] != request_hash:
            raise IdempotencyConflictError(
                f"idempotency key {key!r} in scope {scope!r} was reused with a different request"
            )
        return self._uuid(existing[0])

    @staticmethod
    def _uuid(value: object) -> uuid.UUID:
        """Narrow a database UUID column value (the driver types it Any)."""
        if not isinstance(value, uuid.UUID):
            raise RuntimeError(f"expected a uuid column value, got {type(value).__name__}")
        return value

    def _job_for_key(self, conn: sa.engine.Connection, key_id: uuid.UUID) -> JobRecord | None:
        """Return the job linked to an idempotency key (the reuse fast path), or None."""
        row = conn.execute(sa.select(jobs).where(jobs.c.idempotency_key_id == key_id)).first()
        return job_from_row(row) if row is not None else None

    def _insert_job(
        self, conn: sa.engine.Connection, job: JobRecord, key_id: uuid.UUID | None
    ) -> sa.engine.Row[Any]:
        """Insert the job row and return it (id from the database uuidv7 default)."""
        return conn.execute(
            pg_insert(jobs)
            .values(
                queue=job.queue,
                kind=job.kind,
                payload=pack_payload(job),
                status=physical_status(job.state),
                idempotency_key_id=key_id,
                requested_by_user_id=job.actor_user_id,
            )
            .returning(jobs)
        ).one()

    def get(self, job_id: uuid.UUID) -> JobRecord | None:
        """Return the job (logical states re-expanded), or None."""
        with self._engine.begin() as conn:
            row = conn.execute(sa.select(jobs).where(jobs.c.id == job_id)).first()
        return job_from_row(row) if row is not None else None

    def claim(
        self,
        *,
        worker_id: str,
        capacity_class: str,
        lease_seconds: int,
        policy: CapacityPolicy,
    ) -> JobRecord | None:
        """Claim one queued job of the class under FOR UPDATE SKIP LOCKED + budget checks."""
        budget = policy.budget(CapacityClass(capacity_class))
        with self._engine.begin() as conn:
            chosen = conn.execute(
                sa.text(
                    """
                    WITH candidates AS (
                      SELECT id FROM jobs
                      WHERE status = 'queued' AND queue = :q
                      ORDER BY (payload->>'priority')::int DESC NULLS LAST, enqueued_at ASC
                      LIMIT :batch
                      FOR UPDATE SKIP LOCKED
                    )
                    SELECT c.id FROM candidates c
                    JOIN jobs j2 ON j2.id = c.id
                    WHERE (SELECT count(*) FROM jobs a
                           WHERE a.queue = :q AND a.status IN ('leased','running')) < :class_cap
                      AND (SELECT count(*) FROM jobs a
                           WHERE a.queue = :q AND a.status IN ('leased','running')
                             AND a.requested_by_user_id = j2.requested_by_user_id) < :user_cap
                    LIMIT 1
                    """
                ),
                {
                    "q": capacity_class,
                    "batch": _CLAIM_BATCH,
                    "class_cap": budget.max_concurrent,
                    "user_cap": budget.max_concurrent_per_user,
                },
            ).first()
            if chosen is None:
                return None
            job_id = chosen[0]
            conn.execute(
                sa.text(
                    """
                    UPDATE jobs
                    SET status='leased', lease_owner=:w,
                        lease_expires_at = now() + make_interval(secs => :lease),
                        attempts = attempts + 1, started_at = COALESCE(started_at, now()),
                        revision = revision + 1, etag = (revision + 1)::text, updated_at = now()
                    WHERE id = :id AND status = 'queued'
                    """
                ),
                {"w": worker_id, "lease": lease_seconds, "id": job_id},
            )
            self._record_attempt(conn, job_id, worker_id)
            row = conn.execute(sa.select(jobs).where(jobs.c.id == job_id)).one()
        return job_from_row(row)

    def _record_attempt(
        self, conn: sa.engine.Connection, job_id: uuid.UUID, worker_id: str
    ) -> None:
        """Append the job_attempts row for one claim (attempt_number is 1-based)."""
        conn.execute(
            sa.insert(job_attempts).values(
                job_id=job_id,
                attempt_number=sa.func.coalesce(
                    sa.select(sa.func.max(job_attempts.c.attempt_number)).where(
                        job_attempts.c.job_id == job_id
                    ),
                    0,
                )
                + 1,
                worker_id=worker_id,
                outcome="running",
            )
        )

    def heartbeat(self, job_id: uuid.UUID, worker_id: str, *, lease_seconds: int) -> bool:
        """Extend the lease of a job this worker owns; False when the lease is gone."""
        with self._engine.begin() as conn:
            result = conn.execute(
                sa.text(
                    """
                    UPDATE jobs
                    SET lease_expires_at = now() + make_interval(secs => :lease), updated_at = now()
                    WHERE id = :id AND lease_owner = :w AND status IN ('leased','running')
                    """
                ),
                {"lease": lease_seconds, "id": job_id, "w": worker_id},
            )
        return result.rowcount > 0

    def record_progress(
        self,
        job: JobRecord,
        *,
        progress: JobProgress | None = None,
        checkpoint: dict[str, object] | None = None,
        lease_seconds: int,
    ) -> JobRecord | None:
        """Persist progress/checkpoint and extend the lease in one write; None on lease loss."""
        updated = replace(
            job,
            progress=progress if progress is not None else job.progress,
            checkpoint=checkpoint if checkpoint is not None else job.checkpoint,
            revision=job.revision + 1,
        )
        with self._engine.begin() as conn:
            result = conn.execute(
                sa.text(
                    """
                    UPDATE jobs
                    SET payload = CAST(:payload AS jsonb),
                        lease_expires_at = now() + make_interval(secs => :lease),
                        revision = revision + 1, etag = (revision + 1)::text, updated_at = now()
                    WHERE id = :id AND status IN ('leased','running') AND lease_owner = :owner
                    """
                ),
                {
                    "payload": _json(pack_payload(updated)),
                    "lease": lease_seconds,
                    "id": job.id,
                    "owner": job.lease_owner,
                },
            )
        if result.rowcount == 0:
            return None
        return updated

    def transition(
        self, job: JobRecord, new_state: JobState, **field_updates: object
    ) -> JobRecord:
        """CAS a non-terminal transition; raise JobCasConflictError when the job moved."""
        updated = apply_transition(job, new_state, **field_updates)
        with self._engine.begin() as conn:
            result = conn.execute(
                sa.text(
                    """
                    UPDATE jobs
                    SET status = :status, payload = CAST(:payload AS jsonb),
                        lease_owner = CASE WHEN :release_lease THEN NULL ELSE lease_owner END,
                        lease_expires_at = CASE
                            WHEN :release_lease THEN NULL ELSE lease_expires_at
                        END,
                        revision = revision + 1, etag = (revision + 1)::text, updated_at = now()
                    WHERE id = :id AND status = :expected AND revision = :rev
                    """
                ),
                {
                    "status": physical_status(new_state),
                    "release_lease": new_state in PENDING_STATES or new_state is JobState.QUEUED,
                    "payload": _json(pack_payload(updated)),
                    "id": job.id,
                    "expected": physical_status(job.state),
                    "rev": job.revision,
                },
            )
        if result.rowcount == 0:
            raise JobCasConflictError(
                f"job {job.id} moved under a concurrent writer (expected {job.state.value})"
            )
        return updated

    def complete(
        self,
        job: JobRecord,
        new_state: JobState,
        *,
        result_ref: str | None = None,
        error_code: str | None = None,
        envelope: EventEnvelope,
    ) -> JobRecord:
        """CAS to terminal and publish the terminal event in the SAME transaction."""
        updated = apply_transition(job, new_state, result_ref=result_ref, error_code=error_code)
        with self._engine.begin() as conn:
            result = conn.execute(
                sa.text(
                    """
                    UPDATE jobs
                    SET status = :status, payload = CAST(:payload AS jsonb), finished_at = now(),
                        lease_owner = NULL, lease_expires_at = NULL,
                        revision = revision + 1, etag = (revision + 1)::text, updated_at = now()
                    WHERE id = :id AND status = :expected AND revision = :rev
                    """
                ),
                {
                    "status": new_state.value,
                    "payload": _json(pack_payload(updated)),
                    "id": job.id,
                    "expected": physical_status(job.state),
                    "rev": job.revision,
                },
            )
            if result.rowcount == 0:
                raise JobCasConflictError(
                    f"job {job.id} moved under a concurrent writer (expected {job.state.value})"
                )
            self._finish_attempt(conn, job.id, new_state.value)
            append_outbox(conn, envelope)
        return updated

    def cancel(self, job: JobRecord, *, reason: str, envelope: EventEnvelope) -> JobRecord:
        """CAS to cancelled (any non-terminal) with the event in the same transaction."""
        updated = apply_transition(job, JobState.CANCELLED, cancel_reason=reason)
        with self._engine.begin() as conn:
            result = conn.execute(
                sa.text(
                    """
                    UPDATE jobs
                    SET status = 'cancelled', payload = CAST(:payload AS jsonb),
                        finished_at = now(),
                        lease_owner = NULL, lease_expires_at = NULL,
                        revision = revision + 1, etag = (revision + 1)::text, updated_at = now()
                    WHERE id = :id AND status NOT IN (:s, :f, :c) AND revision = :rev
                    """
                ),
                {
                    "payload": _json(pack_payload(updated)),
                    "id": job.id,
                    "s": JobState.SUCCEEDED.value,
                    "f": JobState.FAILED.value,
                    "c": JobState.CANCELLED.value,
                    "rev": job.revision,
                },
            )
            if result.rowcount == 0:
                raise JobCasConflictError(f"job {job.id} is already terminal")
            self._finish_attempt(conn, job.id, JobState.CANCELLED.value)
            append_outbox(conn, envelope)
        return updated

    def recover_expired(self) -> list[JobRecord]:
        """Reap expired leases: re-queue (attempts left) or fail + publish (attempts spent)."""
        recovered: list[JobRecord] = []
        with self._engine.begin() as conn:
            rows = conn.execute(
                sa.text(
                    """
                    SELECT * FROM jobs
                    WHERE status IN ('leased','running')
                      AND lease_expires_at IS NOT NULL AND lease_expires_at < now()
                    FOR UPDATE SKIP LOCKED
                    """
                )
            ).fetchall()
            for row in rows:
                job = job_from_row(row)
                if job.attempts >= job.max_attempts:
                    failed = apply_transition(job, JobState.FAILED, error_code="lease_expired")
                    conn.execute(
                        sa.text(
                            """
                            UPDATE jobs
                            SET status = 'failed', payload = CAST(:payload AS jsonb),
                                lease_owner = NULL, lease_expires_at = NULL, finished_at = now(),
                                revision = revision + 1, etag = (revision + 1)::text,
                                updated_at = now()
                            WHERE id = :id AND status IN ('leased','running') AND revision = :rev
                            """
                        ),
                        {"payload": _json(pack_payload(failed)), "id": job.id, "rev": job.revision},
                    )
                    self._finish_attempt(conn, job.id, JobState.FAILED.value)
                    append_outbox(
                        conn,
                        EventEnvelope(
                            event_id=uuid.uuid4(),
                            event_type=EVENT_JOB_FAILED,
                            aggregate_kind="job",
                            aggregate_id=job.id,
                            aggregate_version=job.revision,
                            occurred_at=failed.finished_at or datetime.now(tz=UTC),
                            payload=job_event_payload(failed),
                            actor_id=job.actor_user_id,
                            job_id=job.id,
                        ),
                    )
                    recovered.append(failed)
                else:
                    requeued = apply_transition(
                        job, JobState.QUEUED, lease_owner=None, lease_expires_at=None
                    )
                    conn.execute(
                        sa.text(
                            """
                            UPDATE jobs
                            SET status = 'queued', payload = CAST(:payload AS jsonb),
                                lease_owner = NULL, lease_expires_at = NULL,
                                revision = revision + 1, etag = (revision + 1)::text,
                                updated_at = now()
                            WHERE id = :id AND status IN ('leased','running') AND revision = :rev
                            """
                        ),
                        {
                            "payload": _json(pack_payload(requeued)),
                            "id": job.id,
                            "rev": job.revision,
                        },
                    )
                    recovered.append(requeued)
        return recovered

    def _finish_attempt(self, conn: sa.engine.Connection, job_id: uuid.UUID, outcome: str) -> None:
        """Mark the job's current (max-numbered) attempt row with the terminal outcome."""
        conn.execute(
            sa.text(
                """
                UPDATE job_attempts SET outcome = :o, finished_at = now()
                WHERE job_id = :id AND attempt_number = (
                    SELECT max(attempt_number) FROM job_attempts WHERE job_id = :id
                )
                """
            ),
            {"o": outcome, "id": job_id},
        )

    def running_jobs(self, capacity_class: str) -> list[JobRecord]:
        """List leased+running jobs of the class, oldest first (preemption targets)."""
        with self._engine.begin() as conn:
            rows = conn.execute(
                sa.text(
                    """
                    SELECT * FROM jobs
                    WHERE queue = :q AND status IN ('leased','running')
                    ORDER BY enqueued_at ASC
                    """
                ),
                {"q": capacity_class},
            ).fetchall()
        return [job_from_row(row) for row in rows]

    def in_flight(self, capacity_class: str) -> int:
        """Count leased+running jobs of the class (installation-wide)."""
        with self._engine.begin() as conn:
            value = conn.execute(
                sa.text(
                    "SELECT count(*) FROM jobs "
                    "WHERE queue = :q AND status IN ('leased','running')"
                ),
                {"q": capacity_class},
            ).scalar_one()
        return int(value)

    def in_flight_for_user(self, capacity_class: str, user_id: uuid.UUID) -> int:
        """Count leased+running jobs of the class for one user."""
        with self._engine.begin() as conn:
            value = conn.execute(
                sa.text(
                    "SELECT count(*) FROM jobs "
                    "WHERE queue = :q AND status IN ('leased','running') "
                    "AND requested_by_user_id = :u"
                ),
                {"q": capacity_class, "u": user_id},
            ).scalar_one()
        return int(value)


def _json(value: dict[str, object]) -> str:
    """Serialize a payload dict to a JSON string for a CAST(... AS jsonb) parameter."""
    return json.dumps(value, ensure_ascii=True)
