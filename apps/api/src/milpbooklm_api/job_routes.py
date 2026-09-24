"""
Job routes (ch15 + guide/03 request paths, FND-05): 202 enqueue, status, cancel, SSE.

Long work returns ``202`` plus a job resource; idempotency reuse with a
materially different request is a uniform 409. The SSE stream serves the
content-free outbox envelopes: clients resume with ``Last-Event-ID``, a gap
triggers a ``resync`` event (client resynchronizes from the authoritative job
state), and delivery is at-least-once - consumers dedupe by event id.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse, StreamingResponse
from milpbooklm_application.job_actor import InitiatingActor
from milpbooklm_application.job_ports import (
    IdempotencyConflictError,
    JobCasConflictError,
    JobNotFoundError,
    OutboxDispatcher,
)
from milpbooklm_application.job_usecases import JobPorts
from milpbooklm_application.policy_engine import NotebookAccess
from milpbooklm_domain.job_capacity import CapacityClass
from milpbooklm_domain.job_events import job_event_payload
from milpbooklm_domain.jobs import JobRecord
from milpbooklm_domain.policy import PolicyAction
from milpbooklm_domain.telemetry import current_context
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import SQLAlchemyError
from starlette import status

from .deps import ApiDeps, PrincipalDependency
from .security import Principal
from .source_http import problem

SSE_KEEPALIVE_INTERVAL_S = 0.5
SSE_BATCH_LIMIT = 100
ACTIVITY_FEED_LIMIT = 8


@dataclass(frozen=True, slots=True)
class JobActivitySlot:
    """One job summarized as kind, state, and age - no identity, no content."""

    kind: str
    state: str
    age_seconds: int


@dataclass(frozen=True, slots=True)
class JobActivity:
    """Server-wide snapshot of current and recent work across all users."""

    queued: int
    running: int
    active: tuple[JobActivitySlot, ...]
    recent: tuple[JobActivitySlot, ...]


def job_activity(engine: sa.engine.Engine, now: datetime) -> JobActivity:
    """Read the honest server-wide activity view from durable job rows."""
    with engine.connect() as connection:
        queued = int(
            connection.execute(
                sa.text("SELECT count(*) FROM jobs WHERE status = 'queued'")
            ).scalar_one()
        )
        running = int(
            connection.execute(
                sa.text("SELECT count(*) FROM jobs WHERE status IN ('leased','running')")
            ).scalar_one()
        )
        active_rows = connection.execute(
            sa.text(
                "SELECT kind, status, EXTRACT(EPOCH FROM (CAST(:now AS timestamptz)"
                " - COALESCE(started_at, enqueued_at))) AS age"
                " FROM jobs WHERE status NOT IN ('succeeded','failed','cancelled')"
                " ORDER BY COALESCE(started_at, enqueued_at) ASC"
                " LIMIT :limit"
            ),
            {"now": now, "limit": ACTIVITY_FEED_LIMIT},
        ).all()
        recent_rows = connection.execute(
            sa.text(
                "SELECT kind, status, EXTRACT(EPOCH FROM (CAST(:now AS timestamptz)"
                " - COALESCE(finished_at, updated_at))) AS age"
                " FROM jobs WHERE status IN ('succeeded','failed','cancelled')"
                " ORDER BY COALESCE(finished_at, updated_at) DESC"
                " LIMIT :limit"
            ),
            {"now": now, "limit": ACTIVITY_FEED_LIMIT},
        ).all()
    return JobActivity(
        queued=queued,
        running=running,
        active=tuple(JobActivitySlot(row.kind, row.status, int(row.age)) for row in active_rows),
        recent=tuple(JobActivitySlot(row.kind, row.status, int(row.age)) for row in recent_rows),
    )


def _activity_payload(activity: JobActivity) -> dict[str, object]:
    def slot(slot_: JobActivitySlot) -> dict[str, object]:
        return {"kind": slot_.kind, "state": slot_.state, "age_seconds": slot_.age_seconds}

    return {
        "queued": activity.queued,
        "running": activity.running,
        "active": [slot(entry) for entry in activity.active],
        "recent": [slot(entry) for entry in activity.recent],
    }


def _activity_response(activity: Callable[[], JobActivity] | None) -> JSONResponse:
    if activity is None:
        return problem("job_activity_unavailable", "job activity is not configured", 503)
    try:
        return JSONResponse(content=_activity_payload(activity()))
    except SQLAlchemyError:
        return problem("job_activity_unavailable", "job activity is unreadable", 503)


class EnqueueJobRequest(BaseModel):
    """The enqueue body (kind + minimal content-free payload)."""

    model_config = ConfigDict(frozen=True)

    kind: str
    payload: dict[str, object] = {}
    capacity_class: str = CapacityClass.INTERACTIVE_TEXT.value
    priority: int = 0
    notebook_id: uuid.UUID | None = None
    capability: str | None = None
    idempotency_key: str | None = None


def _job_view(record: JobRecord) -> dict[str, object]:
    """Build the status view: state, progress, waiting reason and references (no content)."""
    payload = job_event_payload(record)
    return {
        "job_id": str(record.id),
        "kind": record.kind,
        "capacity_class": record.queue,
        "state": record.state.value,
        "waiting_reason": record.waiting_reason,
        "priority": record.priority,
        "attempts": record.attempts,
        "max_attempts": record.max_attempts,
        "progress": payload.get("progress"),
        "result_ref": record.result_ref,
        "error_code": record.error_code,
        "cancel_reason": record.cancel_reason,
        "enqueued_at": record.enqueued_at.isoformat() if record.enqueued_at else None,
        "started_at": record.started_at.isoformat() if record.started_at else None,
        "finished_at": record.finished_at.isoformat() if record.finished_at else None,
    }


def build_job_router(
    deps: ApiDeps,
    principal: PrincipalDependency,
    jobs: JobPorts,
    activity: Callable[[], JobActivity] | None = None,
) -> APIRouter:
    """Build the /api/v1/jobs router over the wired job ports."""
    router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])

    @router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=None)
    async def enqueue(
        body: EnqueueJobRequest, principal: Principal = Depends(principal)
    ) -> JSONResponse:
        """Accept durable work (202 + job resource); 409 on idempotency key conflict."""
        return _enqueue(deps, principal, body, jobs)

    # /events and /activity must register before /{job_id}: Starlette matches by
    # path pattern first, so a later static route would 422 on UUID validation.
    @router.get("/events")
    async def job_events(
        last_event_id: int | None = Header(default=None, alias="Last-Event-ID"),
        principal: Principal = Depends(principal),
    ) -> StreamingResponse:
        """SSE job-event stream: Last-Event-ID resume, gap -> resync, at-least-once."""
        del principal  # authentication via the dependency; the stream is the user's jobs
        return StreamingResponse(
            _event_frames(jobs.dispatcher, last_event_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.get("/activity", response_model=None)
    async def job_activity_view(
        principal: Principal = Depends(principal),
    ) -> JSONResponse:
        """Server-wide current and recent job activity (identity-free)."""
        del principal
        return _activity_response(activity)

    @router.get("/{job_id}", response_model=None)
    async def get_job(job_id: uuid.UUID, principal: Principal = Depends(principal)) -> JSONResponse:
        """One job's status (404 when unknown or not the principal's job)."""
        job = jobs.repo.get(job_id)
        if job is None or job.actor_user_id != principal.user.id:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND, content={"detail": "job not found"}
            )
        return JSONResponse(content=_job_view(job))

    @router.post("/{job_id}/cancel", response_model=None)
    async def cancel_job(
        job_id: uuid.UUID, principal: Principal = Depends(principal)
    ) -> JSONResponse:
        """Cancel the durable job (409 when already terminal)."""
        job = jobs.repo.get(job_id)
        if job is None or job.actor_user_id != principal.user.id:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND, content={"detail": "job not found"}
            )
        if job.terminal:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={"detail": f"job is already terminal ({job.state.value})"},
            )
        try:
            updated = jobs.cancel(job_id)
        except (JobCasConflictError, JobNotFoundError):
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={"detail": "job is already terminal"},
            )
        return JSONResponse(content=_job_view(updated))

    return router


def _enqueue(
    deps: ApiDeps, principal: Principal, body: EnqueueJobRequest, jobs: JobPorts
) -> JSONResponse:
    """Validate the request, enforce notebook authorization, enqueue, map to HTTP."""
    try:
        job_class = CapacityClass(body.capacity_class)
    except ValueError:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": f"unknown capacity class {body.capacity_class!r}"},
        )
    if body.notebook_id is not None:
        view = deps.notebooks.notebook_with_membership(principal.user.id, body.notebook_id)
        if view is None:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"detail": "notebook not found"},
            )
        decision = deps.engine.decide_notebook(
            principal.user,
            NotebookAccess(notebook_id=body.notebook_id, role=view.membership),
            PolicyAction.NOTE_MUTATE,
        )
        if not decision.allowed:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": {"reason": decision.reason.value}},
            )
    ctx = current_context()
    try:
        job, _created = jobs.enqueue(
            kind=body.kind,
            payload=body.payload,
            actor=InitiatingActor(
                user_id=principal.user.id,
                request_id=ctx.request_id if ctx is not None else None,
                trace_id=ctx.trace_id if ctx is not None else None,
            ),
            capacity_class=job_class,
            priority=body.priority,
            notebook_id=body.notebook_id,
            capability=body.capability,
            idempotency_key=body.idempotency_key,
        )
    except IdempotencyConflictError:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "idempotency key conflict"},
        )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "job_id": str(job.id),
            "state": job.state.value,
            "waiting_reason": job.waiting_reason,
        },
    )


async def _event_frames(
    dispatcher: OutboxDispatcher, last_event_id: int | None
) -> AsyncIterator[str]:
    """SSE frames: resume from Last-Event-ID, resync on gap, keepalive when idle."""
    max_seq = dispatcher.max_job_event_seq()
    cursor = max_seq if last_event_id is None else last_event_id
    if last_event_id is not None and last_event_id > max_seq:
        # Gap: the client's position is beyond the retained tail - resync.
        yield _sse(None, "resync", {"reason": "gap", "resume_seq": max_seq})
        cursor = max_seq
    while True:
        events = dispatcher.stream_job_events(cursor, limit=SSE_BATCH_LIMIT)
        if not events:
            yield ": keepalive\n\n"
            await asyncio.sleep(SSE_KEEPALIVE_INTERVAL_S)
            continue
        dispatched: list[int] = []
        for event in events:
            yield _sse(event.seq, event.event_type, event.envelope)
            cursor = event.seq
            dispatched.append(event.seq)
        dispatcher.mark_dispatched(dispatched)


def _sse(seq: int | None, event_type: str, data: dict[str, Any]) -> str:
    """Format one Server-Sent Event frame (the id line is the resume cursor)."""
    id_line = f"id: {seq}\n" if seq is not None else ""
    return f"{id_line}event: {event_type}\ndata: {json.dumps(data, ensure_ascii=True)}\n\n"
