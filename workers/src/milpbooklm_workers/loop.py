"""
The worker loop (ch15, FND-05): recover, claim, execute, complete.

Each poll: reap expired leases (the reaper is CAS-guarded, so a slow worker that
wakes up loses the race), then claim one job per configured capacity class under
the class/per-user budgets. For each claimed job the loop revalidates the actor's
authorization before dispatch, moves leased -> running (CAS), runs the handler
with durable progress/checkpoint heartbeats, revalidates again before publication,
and publishes the terminal state + event atomically. Handler kinds are executed by
idempotent handlers: lease recovery re-runs them safely (checkpoint resume).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping, Sequence

from milpbooklm_application.job_ports import AuthzRevalidator, JobCasConflictError, JobRepository
from milpbooklm_application.job_usecases import (
    CancelJob,
    CompleteJob,
    RecoverExpiredLeases,
)
from milpbooklm_domain.job_capacity import CapacityPolicy
from milpbooklm_domain.jobs import JobProgress, JobRecord, JobState
from milpbooklm_domain.telemetry import (
    CorrelationContext,
    bind_context,
    new_request_id,
    new_span_id,
    reset_context,
)

from milpbooklm_workers.handlers import HandlerCancelledError, JobHandler, JobResult

logger = logging.getLogger(__name__)


class _LoopContext:
    """JobContext for the loop: durable progress/checkpoint writes + lease-loss signal."""

    def __init__(self, repo: JobRepository, job: JobRecord, lease_seconds: int) -> None:
        """Wire the repository and the job this context reports on."""
        self._repo = repo
        self._job: JobRecord | None = job
        self._lease_seconds = lease_seconds

    def checkpoint(self, data: dict[str, object]) -> None:
        """Persist the durable stage checkpoint (also extends the lease)."""
        if self._job is None:
            return
        self._update(checkpoint=data)

    def progress(self, phase: str, fraction: float | None, status: str | None) -> None:
        """Persist user-visible progress (also extends the lease)."""
        if self._job is None:
            return
        self._update(progress=JobProgress(phase=phase, fraction=fraction, status=status))

    def should_stop(self) -> bool:
        """Return True when the job was cancelled or the lease was lost (reaper took over)."""
        return self._job is None

    def _update(
        self,
        *,
        progress: JobProgress | None = None,
        checkpoint: dict[str, object] | None = None,
    ) -> None:
        if self._job is None:
            return
        updated = self._repo.record_progress(
            self._job,
            progress=progress,
            checkpoint=checkpoint,
            lease_seconds=self._lease_seconds,
        )
        if updated is None:
            logger.info("lease lost for job %s; stopping cooperatively", self._job.id)
            self._job = None
        else:
            self._job = updated


class WorkerLoop:
    """One worker process: the durable poll-claim-run-publish cycle (ch15)."""

    def __init__(
        self,
        *,
        repo: JobRepository,
        handlers: Mapping[str, JobHandler],
        policy: CapacityPolicy,
        worker_id: str,
        capacity_classes: Sequence[str],
        lease_seconds: int,
        poll_seconds: float,
        complete: CompleteJob,
        recover: RecoverExpiredLeases,
        cancel: CancelJob,
        revalidator: AuthzRevalidator | None = None,
    ) -> None:
        """Wire the ports, the handler table, and the loop's timing/identity."""
        self._repo = repo
        self._handlers = dict(handlers)
        self._policy = policy
        self._worker_id = worker_id
        self._classes = tuple(capacity_classes)
        self._lease_seconds = lease_seconds
        self._poll_seconds = poll_seconds
        self._publish = complete
        self._recover = recover
        self._cancel = cancel
        self._revalidator = revalidator
        self._stopping = False

    def request_stop(self) -> None:
        """Ask the loop to exit after the current poll (SIGINT/SIGTERM)."""
        self._stopping = True
        logger.info("stop requested for worker %s", self._worker_id)

    @property
    def worker_id(self) -> str:
        """The worker's durable lease identity."""
        return self._worker_id

    def run_forever(self) -> None:
        """Run until request_stop(); one poll per cycle, then sleep."""
        logger.info(
            "worker %s starting (queues=%s, lease=%ss, poll=%.2fs)",
            self._worker_id,
            ",".join(self._classes),
            self._lease_seconds,
            self._poll_seconds,
        )
        while not self._stopping:
            self._poll_once()
            if not self._stopping:
                time.sleep(self._poll_seconds)
        logger.info("worker %s stopped", self._worker_id)

    def _poll_once(self) -> None:
        """Recover expired leases, then claim + run one job per class."""
        for recovered in self._recover():
            logger.info(
                "recovered expired lease for job %s (state=%s, attempts=%d)",
                recovered.id,
                recovered.state.value,
                recovered.attempts,
            )
        for capacity_class in self._classes:
            if self._stopping:
                break
            claimed = self._repo.claim(
                worker_id=self._worker_id,
                capacity_class=capacity_class,
                lease_seconds=self._lease_seconds,
                policy=self._policy,
            )
            if claimed is not None:
                self._run_one(claimed)

    def _run_one(self, job: JobRecord) -> None:
        """Execute one claimed job end-to-end (dispatch check -> run -> publish check)."""
        token = bind_context(
            CorrelationContext(
                request_id=job.request_id or new_request_id(),
                trace_id=job.trace_id,
                span_id=new_span_id(),
                trace_flags="01" if job.trace_id is not None else None,
            )
        )
        try:
            self._execute(job)
        finally:
            reset_context(token)

    def _execute(self, job: JobRecord) -> None:
        """Run the claim->authz->run->publish sequence for one job (context already bound)."""
        handler = self._handlers.get(job.kind)
        if handler is None:
            logger.warning("no handler for job kind %s; failing job %s", job.kind, job.id)
            self._fail(job, error_code="unknown_handler")
            return
        logger.info(
            "claimed job %s (kind=%s, class=%s, attempt=%d)",
            job.id,
            job.kind,
            job.queue,
            job.attempts,
        )
        if not self._authz_ok(job):
            self._cancel_job(job, reason="authorization_revoked")
            return
        try:
            running = self._repo.transition(job, JobState.RUNNING)
        except JobCasConflictError:
            logger.info("job %s moved before dispatch; not running it", job.id)
            return
        context = _LoopContext(self._repo, running, self._lease_seconds)
        try:
            result = handler.run(running, context)
        except HandlerCancelledError:
            logger.info("job %s cancelled cooperatively", job.id)
            return
        except Exception:
            logger.exception("handler for job %s raised; failing the job", job.id)
            current = self._repo.get(job.id)
            if current is not None and not current.terminal:
                self._fail(current, error_code="handler_error")
            return
        self._publish_result(job, result)

    def _publish_result(self, job: JobRecord, result: JobResult) -> None:
        """Publication check: re-read (progress writes moved the revision) + revalidate."""
        current = self._repo.get(job.id)
        if current is None or current.terminal:
            logger.info("job %s is already terminal before publish; not publishing", job.id)
            return
        if not self._authz_ok(current):
            self._cancel_job(current, reason="authorization_revoked")
            return
        self._succeed(current, result)

    def _succeed(self, job: JobRecord, result: JobResult) -> None:
        """Publish the succeeded terminal state, tolerating a CAS loss to a concurrent writer."""
        try:
            self._publish(job, succeeded=True, result_ref=result.result_ref)
        except JobCasConflictError:
            logger.info("terminal publish for job %s lost the CAS race", job.id)

    def _fail(self, job: JobRecord, *, error_code: str) -> None:
        """Publish the failed terminal state, tolerating a CAS loss to a concurrent writer."""
        try:
            self._publish(job, succeeded=False, error_code=error_code)
        except JobCasConflictError:
            logger.info("terminal publish for job %s lost the CAS race", job.id)

    def _cancel_job(self, job: JobRecord, *, reason: str) -> None:
        """Cancel durably, tolerating a CAS loss (a terminal writer beat us)."""
        try:
            self._cancel(job.id, reason=reason)
        except JobCasConflictError:
            logger.info("cancel for job %s lost the CAS race", job.id)

    def _authz_ok(self, job: JobRecord) -> bool:
        """Check the actor's current authorization (system jobs without an actor pass)."""
        return self._revalidator is None or self._revalidator.revalidate(job)
