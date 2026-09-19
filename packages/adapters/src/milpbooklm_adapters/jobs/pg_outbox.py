"""
Outbox adapter: same-transaction append + the monotonic-sequence read side (ch15, FND-05).

``append_outbox`` joins the CALLER's open transaction, which is what makes terminal
publication atomic: the job's terminal row and its outbox event commit together, so
a job can never be terminal without its event (or vice versa). The dispatcher side
reads the job-event stream by the global identity ``seq`` (monotonic; every per-job
stream sees a monotonic subsequence) and marks delivery for at-least-once semantics.
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from milpbooklm_application.job_ports import OutboxEvent
from milpbooklm_domain.job_events import JOB_AGGREGATE_KIND, EventEnvelope

from milpbooklm_adapters.db.tables.ops import outbox_events


def append_outbox(conn: sa.engine.Connection, envelope: EventEnvelope) -> int:
    """Insert one envelope into the caller's open transaction; return the assigned seq."""
    row = conn.execute(
        sa.insert(outbox_events)
        .values(
            aggregate_kind=envelope.aggregate_kind,
            aggregate_id=envelope.aggregate_id,
            event_type=envelope.event_type,
            payload=envelope.to_dict(),
        )
        .returning(outbox_events.c.seq)
    ).one()
    return int(row.seq)


def _to_event(row: sa.engine.Row[Any]) -> OutboxEvent:
    """Map one outbox row to the port's value object."""
    return OutboxEvent(
        seq=int(row.seq),
        event_id=row.id,
        event_type=row.event_type,
        aggregate_id=row.aggregate_id,
        occurred_at=row.created_at,
        envelope=dict(row.payload),
    )


class PgOutboxDispatcher:
    """The outbox_events table adapter implementing the OutboxDispatcher port."""

    def __init__(self, engine: sa.engine.Engine) -> None:
        """Wire the engine."""
        self._engine = engine

    def stream_job_events(self, after_seq: int, *, limit: int = 100) -> list[OutboxEvent]:
        """Return job events with seq > after_seq, in sequence order (SSE resume)."""
        with self._engine.begin() as conn:
            rows = conn.execute(
                sa.select(outbox_events)
                .where(
                    outbox_events.c.aggregate_kind == JOB_AGGREGATE_KIND,
                    outbox_events.c.seq > after_seq,
                )
                .order_by(outbox_events.c.seq)
                .limit(limit)
            ).fetchall()
        return [_to_event(row) for row in rows]

    def job_events_since(
        self, job_id: uuid.UUID, after_seq: int, *, limit: int = 100
    ) -> list[OutboxEvent]:
        """Return one job's event stream (per-job monotonic) with seq > after_seq."""
        with self._engine.begin() as conn:
            rows = conn.execute(
                sa.select(outbox_events)
                .where(
                    outbox_events.c.aggregate_kind == JOB_AGGREGATE_KIND,
                    outbox_events.c.aggregate_id == job_id,
                    outbox_events.c.seq > after_seq,
                )
                .order_by(outbox_events.c.seq)
                .limit(limit)
            ).fetchall()
        return [_to_event(row) for row in rows]

    def max_job_event_seq(self) -> int:
        """Return the highest job-event stream sequence (0 when the stream is empty)."""
        with self._engine.begin() as conn:
            value = conn.execute(
                sa.select(sa.func.max(outbox_events.c.seq)).where(
                    outbox_events.c.aggregate_kind == JOB_AGGREGATE_KIND
                )
            ).scalar_one()
        return int(value) if value is not None else 0

    def mark_dispatched(self, seqs: list[int]) -> None:
        """Mark rows delivered (idempotent; at-least-once, consumers dedupe by event id)."""
        if not seqs:
            return
        with self._engine.begin() as conn:
            conn.execute(
                sa.update(outbox_events)
                .where(outbox_events.c.seq.in_(seqs))
                .values(dispatched=True, dispatched_at=sa.func.now())
            )
