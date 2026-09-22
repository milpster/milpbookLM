"""The research.execute job handler: drives one run's executor (RSR-01b)."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass

from milpbooklm_application.research_executor import ResearchRunExecutor
from milpbooklm_domain.jobs import JobRecord

from milpbooklm_workers.handlers import JobContext, JobResult


@dataclass(frozen=True, slots=True)
class ResearchSession:
    """One per-job executor plus its async service teardown."""

    executor: ResearchRunExecutor
    aclose: Callable[[], Coroutine[None, None, None]]


class ResearchRunHandler:
    """Claim a run's orchestrator job and execute steps to a boundary."""

    kind = "research.execute"

    def __init__(self, session_factory: Callable[[], ResearchSession]) -> None:
        """Wire the per-job session factory (fresh async services each time)."""
        self._open_session = session_factory

    def run(self, job: JobRecord, context: JobContext) -> JobResult:
        """Execute the run inside one event loop; durable state stays resumable."""
        run_id = _payload_run_id(job)
        session = self._open_session()
        try:
            outcome = asyncio.run(
                session.executor.execute(
                    run_id,
                    should_stop=context.should_stop,
                    checkpoint=context.checkpoint,
                    progress=context.progress,
                )
            )
        finally:
            asyncio.run(session.aclose())
        return JobResult(
            result_ref=(
                f"research-run:{run_id}:{outcome.run_status.value}:"
                f"steps={outcome.steps_executed}:evidence={outcome.evidence_appended}"
            )
        )


def _payload_run_id(job: JobRecord) -> uuid.UUID:
    value = job.payload.get("run_id")
    if not isinstance(value, str):
        raise ValueError("research.execute payload is missing run_id")
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ValueError(f"research.execute payload run_id is invalid: {value!r}") from exc
