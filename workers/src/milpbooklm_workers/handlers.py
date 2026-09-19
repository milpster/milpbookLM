"""
Job handlers: the execution seam between the worker loop and job kinds (FND-05).

A handler receives the durable JobRecord (its checkpoint, if any, is restored by
the loop after lease recovery) and reports progress/checkpoints through the
context. Handlers must be idempotent with respect to re-execution after lease
recovery (ch15: expired leases are recoverable only for idempotent/resumable
handlers) - the demo handler is a pure function of its payload plus its own
durable checkpoint, so a recovered re-run resumes where the dead worker stopped.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Protocol

from milpbooklm_domain.jobs import JobRecord


class HandlerCancelledError(RuntimeError):
    """Cooperative cancellation: the job row is already cancelled (do not complete)."""


@dataclass(frozen=True, slots=True)
class JobResult:
    """A handler's outcome: a result reference (never the result content itself)."""

    result_ref: str | None = None


class JobContext(Protocol):
    """The loop's seam into a running job: durable progress/checkpoint + stop signal."""

    def checkpoint(self, data: dict[str, object]) -> None:
        """Persist a durable stage checkpoint (survives worker crashes)."""
        ...

    def progress(self, phase: str, fraction: float | None, status: str | None) -> None:
        """Persist user-visible progress (phase, measurable fraction, status text)."""
        ...

    def should_stop(self) -> bool:
        """Return True when the job was cancelled or the lease was lost (stop)."""
        ...


class JobHandler(Protocol):
    """One durable job kind's execution logic."""

    kind: str

    def run(self, job: JobRecord, context: JobContext) -> JobResult:
        """Execute the job (idempotent under re-execution); return the result reference."""
        ...


_DEMO_STEP_MS = 50


class DemoEchoHandler:
    """
    The demo job kind (QA + wiring proof): a deterministic echo of its payload.

    Idempotent by construction - the result is a pure function of the payload, and
    the durable checkpoint (processed_ms) lets a recovered worker resume instead of
    restarting, so a job completes exactly once end-to-end.
    """

    kind = "demo.echo"

    def run(self, job: JobRecord, context: JobContext) -> JobResult:
        """Echo the payload text after a checkpointed, cancellable work loop."""
        text = str(job.payload.get("text", ""))
        sleep_raw = job.payload.get("sleep_ms")
        total_ms = max(1, sleep_raw if isinstance(sleep_raw, int) else 200)
        checkpoint = job.checkpoint or {}
        done_raw = checkpoint.get("processed_ms")
        done_ms = done_raw if isinstance(done_raw, int) else 0
        while done_ms < total_ms:
            if context.should_stop():
                raise HandlerCancelledError()
            time.sleep(0.05)
            done_ms = min(total_ms, done_ms + _DEMO_STEP_MS)
            context.checkpoint({"processed_ms": done_ms, "stage": "processing"})
            context.progress("processing", done_ms / total_ms, "echoing")
        context.progress("done", 1.0, "complete")
        result = {"echo": text, "length": len(text)}
        return JobResult(result_ref=json.dumps(result, sort_keys=True))
