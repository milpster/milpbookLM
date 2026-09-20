"""
Versioned job event envelope (ch15 "Outbox/SSE", FND-05).

The envelope is the ONLY shape that crosses the outbox and the SSE stream.
Payloads are content-free by construction: ids, references, statuses and
progress numbers - never provider credentials, tokens, or unrestricted source
text. ``assert_content_free`` is a structural guard that rejects any envelope
whose payload carries a forbidden key, so a future handler cannot smuggle
credentials or source text into a durable event (ARCH-15-015/016, ch15 MUST NOT).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from milpbooklm_domain.jobs import JobRecord

ENVELOPE_SCHEMA_VERSION = 1

JOB_AGGREGATE_KIND = "job"

# Event types the baseline job system emits (durable, content-free).
EVENT_JOB_ENQUEUED = "job.enqueued"
EVENT_JOB_STARTED = "job.started"
EVENT_JOB_SUCCEEDED = "job.succeeded"
EVENT_JOB_FAILED = "job.failed"
EVENT_JOB_CANCELLED = "job.cancelled"

TERMINAL_EVENT_TYPES: frozenset[str] = frozenset(
    {EVENT_JOB_SUCCEEDED, EVENT_JOB_FAILED, EVENT_JOB_CANCELLED}
)

# Key fragments that must never appear in an event payload (any depth):
# credential material and unrestricted source text (ch15 MUST NOT).
_FORBIDDEN_KEY_FRAGMENTS: tuple[str, ...] = (
    "password",
    "credential",
    "api_key",
    "apikey",
    "access_token",
    "secret",
    "token",
    "source_text",
    "content",
)


class EventPayloadNotContentFreeError(ValueError):
    """An event payload carries credential/source-text keys; publication must be refused."""


def assert_content_free(payload: dict[str, object]) -> None:
    """
    Reject a payload that contains a forbidden key at any nesting depth.

    Raises :class:`EventPayloadNotContentFreeError` naming the first offending path.
    """
    for key, value in payload.items():
        lowered = key.lower()
        if any(fragment in lowered for fragment in _FORBIDDEN_KEY_FRAGMENTS):
            raise EventPayloadNotContentFreeError(f"event payload key {key!r} is not content-free")
        if isinstance(value, dict):
            assert_content_free(value)


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    """
    One durable job event (ch15: stable id, schema version, type, aggregate).

    Carries stream sequence, correlation ids and a content-free payload.
    ``stream_seq`` is 0 until the outbox dispatcher stamps the per-stream
    monotonic sequence at insertion; ``payload`` carries only references.
    """

    event_id: uuid.UUID
    event_type: str
    aggregate_kind: str
    aggregate_id: uuid.UUID
    aggregate_version: int
    occurred_at: datetime
    payload: dict[str, object] = field(default_factory=dict)
    schema_version: int = ENVELOPE_SCHEMA_VERSION
    stream_seq: int = 0
    actor_id: uuid.UUID | None = None
    operation_id: str | None = None
    trace_id: str | None = None
    job_id: uuid.UUID | None = None
    visibility: str = "private"

    def to_dict(self) -> dict[str, object]:
        """Serialize to the wire/JSONB shape (the SSE ``data`` body)."""
        assert_content_free(self.payload)
        return {
            "schema_version": self.schema_version,
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "aggregate_kind": self.aggregate_kind,
            "aggregate_id": str(self.aggregate_id),
            "aggregate_version": self.aggregate_version,
            "stream_seq": self.stream_seq,
            "occurred_at": self.occurred_at.isoformat(),
            "actor_id": str(self.actor_id) if self.actor_id is not None else None,
            "operation_id": self.operation_id,
            "trace_id": self.trace_id,
            "job_id": str(self.job_id) if self.job_id is not None else None,
            "visibility": self.visibility,
            "payload": self.payload,
        }


def job_event_payload(job: JobRecord) -> dict[str, object]:
    """
    Build the content-free payload for one job event from a JobRecord.

    Carries state, progress and references only (ch15: minimal payload; large
    or sensitive material is referenced by authorized id, never copied).
    """
    payload: dict[str, object] = {
        "job_id": str(job.id),
        "kind": job.kind,
        "capacity_class": job.queue,
        "state": job.state.value,
        "attempts": job.attempts,
        "priority": job.priority,
        "notebook_id": str(job.notebook_id) if job.notebook_id is not None else None,
        "result_ref": job.result_ref,
        "error_code": job.error_code,
        "waiting_reason": job.waiting_reason,
    }
    if job.progress is not None:
        payload["progress"] = {
            "phase": job.progress.phase,
            "fraction": job.progress.fraction,
            "status": job.progress.status,
        }
    if job.cancel_reason is not None:
        payload["cancel_reason"] = job.cancel_reason
    return payload
