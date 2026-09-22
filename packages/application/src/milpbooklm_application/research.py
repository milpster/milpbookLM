"""
Research run state machine use cases (RSR-01b, guide/11 Separation).

Research runs are durable state machines DISTINCT from chat: creation freezes
an explicit mode/budget/tools configuration into the run row, and every later
transition (start/pause/resume/cancel, terminal publication) is a
compare-and-swap against the stored status - request handlers never drive
step execution directly (single-owner lifecycle: the ``research.execute``
worker job owns the loop). Side-effect tools require the actor's approval,
recorded on the run at creation and enforced server-side by the executor.
"""

from __future__ import annotations

import contextlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from milpbooklm_domain.jobs import CapacityClass
from milpbooklm_domain.research import (
    RESEARCH_TOOL_SURFACE,
    SIDE_EFFECT_TOOLS,
    ResearchBudget,
    ResearchRunStatus,
    RunMode,
    run_transition_allowed,
)

from .job_actor import InitiatingActor
from .job_ports import JobCasConflictError
from .job_usecases import JobPorts

RESEARCH_EXECUTE_KIND = "research.execute"


class ResearchRunError(RuntimeError):
    """Base class for typed research run failures."""


class ResearchRunNotFoundError(LookupError):
    """The run is unknown or outside the actor's ownership."""


class ResearchRunCasConflictError(RuntimeError):
    """A run transition lost the compare-and-swap (concurrent writer)."""


class InvalidRunConfigError(ValueError):
    """The requested mode/tools/approval configuration is not admissible."""


@dataclass(frozen=True, slots=True)
class RunControlResult:
    """One control-command outcome: the run, the enqueued job (if any), conflict."""

    run: ResearchRunView
    job_id: str | None
    conflict: bool


@dataclass(frozen=True, slots=True)
class ResearchRunView:
    """The authoritative run state (config + status; step history lives in the store)."""

    run_id: uuid.UUID
    notebook_id: uuid.UUID
    actor_id: uuid.UUID
    goal: str
    mode: RunMode
    status: ResearchRunStatus
    tools: frozenset[str]
    approved_tools: frozenset[str]
    budget: ResearchBudget
    error_code: str | None
    started_at: datetime | None
    finished_at: datetime | None
    revision: int
    created_at: datetime | None
    updated_at: datetime | None
    plan: dict[str, object] | None = None
    candidate_imports: list[object] | None = None


@dataclass(frozen=True, slots=True)
class ResearchStepView:
    """One append-only run step (planning/model/tool) with its manifest reference."""

    step_id: uuid.UUID
    run_id: uuid.UUID
    step_number: int
    step_kind: str
    tool_name: str | None
    status: str
    input_manifest: dict[str, object] | None
    tool_result: dict[str, object] | None
    error_code: str | None
    evidence_snapshot_id: uuid.UUID | None
    started_at: datetime | None
    finished_at: datetime | None


@dataclass(frozen=True, slots=True)
class EvidenceSnapshotView:
    """One immutable evidence record appended per tool output."""

    evidence_id: uuid.UUID
    run_id: uuid.UUID
    origin_tool: str
    origin_locator: str | None
    content_sha256: str
    blob_id: uuid.UUID | None
    locators: dict[str, object] | None
    access_metadata: dict[str, object] | None
    promoted_source_version_id: uuid.UUID | None
    acquired_at: datetime


class ResearchRunStore(Protocol):
    """Durable research run persistence (research_runs/run_steps/evidence)."""

    def create_run(self, run: ResearchRunView, initial_snapshot: dict[str, object]) -> None:
        """Insert the run row with its frozen initial input snapshot."""
        ...

    def get_run(self, run_id: uuid.UUID) -> ResearchRunView | None:
        """Load one run (logical view; None when absent)."""
        ...

    def cas_status(
        self,
        run_id: uuid.UUID,
        expected: ResearchRunStatus,
        target: ResearchRunStatus,
        *,
        field_updates: dict[str, object] | None = None,
    ) -> ResearchRunView | None:
        """
        CAS the run status; None when the expected status no longer holds.

        ``field_updates`` carries only run-view fields (closed vocabulary:
        started_at/finished_at datetimes, error_code, plan, candidate_imports).
        """
        ...

    def insert_step(self, step: ResearchStepView) -> None:
        """Append one step row (step_number uniqueness is per-run)."""
        ...

    def finish_step(
        self,
        step_id: uuid.UUID,
        *,
        status: str,
        tool_result: dict[str, object] | None = None,
        error_code: str | None = None,
        evidence_snapshot_id: uuid.UUID | None = None,
    ) -> None:
        """Complete a step row (status/evidence linkage)."""
        ...

    def append_evidence(
        self,
        run_id: uuid.UUID,
        *,
        origin_tool: str,
        content_sha256: str,
        origin_locator: str | None = None,
        blob_id: uuid.UUID | None = None,
        locators: dict[str, object] | None = None,
        access_metadata: dict[str, object] | None = None,
    ) -> EvidenceSnapshotView:
        """Append one immutable evidence snapshot (append-only by trigger)."""
        ...

    def mark_promoted(self, evidence_id: uuid.UUID, source_version_id: uuid.UUID) -> bool:
        """One-time promotion link on an evidence snapshot; False when already set."""
        ...

    def list_steps(self, run_id: uuid.UUID) -> list[ResearchStepView]:
        """Return the run's steps in step_number order."""
        ...

    def list_evidence(self, run_id: uuid.UUID) -> list[EvidenceSnapshotView]:
        """Return the run's immutable evidence records in append order."""
        ...


def _validate_run_config(
    mode: RunMode, tools: frozenset[str], approved: frozenset[str], budget: ResearchBudget
) -> None:
    """Reject tools outside the seven-tool surface and unapproved side effects."""
    unknown = tools - RESEARCH_TOOL_SURFACE
    if unknown:
        raise InvalidRunConfigError(f"tools outside the research tool surface: {sorted(unknown)}")
    if not tools:
        raise InvalidRunConfigError("a run must enable at least one tool")
    unapproved_side_effects = approved - tools
    if unapproved_side_effects:
        raise InvalidRunConfigError(
            f"approved tools not enabled on the run: {sorted(unapproved_side_effects)}"
        )
    side_effect_approval = SIDE_EFFECT_TOOLS & tools - approved
    if side_effect_approval:
        raise InvalidRunConfigError(
            f"side-effect tools require explicit approval: {sorted(side_effect_approval)}"
        )
    if mode not in set(RunMode):
        raise InvalidRunConfigError(f"unknown research mode: {mode}")


class CreateResearchRun:
    """Freeze an explicitly configured run (created state, immutable snapshot)."""

    def __init__(self, store: ResearchRunStore) -> None:
        """Wire the run store."""
        self._store = store

    def __call__(
        self,
        *,
        actor_id: uuid.UUID,
        notebook_id: uuid.UUID,
        goal: str,
        mode: RunMode,
        tools: frozenset[str],
        approved_tools: frozenset[str],
        budget: ResearchBudget,
    ) -> ResearchRunView:
        """Validate the configuration and persist the created run."""
        _validate_run_config(mode, tools, approved_tools, budget)
        now = datetime.now(tz=UTC)
        run = ResearchRunView(
            run_id=uuid.uuid4(),
            notebook_id=notebook_id,
            actor_id=actor_id,
            goal=goal,
            mode=mode,
            status=ResearchRunStatus.CREATED,
            tools=frozenset(tools),
            approved_tools=frozenset(approved_tools),
            budget=budget,
            error_code=None,
            started_at=None,
            finished_at=None,
            revision=0,
            created_at=now,
            updated_at=now,
        )
        initial_snapshot: dict[str, object] = {
            "goal": goal,
            "mode": mode.value,
            "tools": sorted(tools),
            "approved_tools": sorted(approved_tools),
            "budget": {
                "max_steps": budget.max_steps,
                "max_tool_calls": budget.max_tool_calls,
                "max_imports": budget.max_imports,
            },
        }
        self._store.create_run(run, initial_snapshot)
        return run


def _enqueue_execution(jobs: JobPorts, run: ResearchRunView, actor: InitiatingActor) -> str:
    """Enqueue (or idempotently reuse) the run's orchestrator job; return its id."""
    job, _created = jobs.enqueue(
        kind=RESEARCH_EXECUTE_KIND,
        payload={"run_id": str(run.run_id)},
        actor=actor,
        capacity_class=CapacityClass.RESEARCH_BROWSER,
        notebook_id=run.notebook_id,
        capability="research_run",
        idempotency_key=f"{RESEARCH_EXECUTE_KIND}:{run.run_id}:{run.revision}",
    )
    return str(job.id)


class StartResearchRun:
    """CAS created -> running and hand execution to the worker (202 path)."""

    def __init__(self, store: ResearchRunStore, jobs: JobPorts) -> None:
        """Wire the run store and the job ports."""
        self._store = store
        self._jobs = jobs

    def __call__(
        self, actor_id: uuid.UUID, run_id: uuid.UUID, actor: InitiatingActor
    ) -> RunControlResult | None:
        """Start the run; None when absent, conflict=True on a CAS loss."""
        run = self._store.get_run(run_id)
        if run is None or run.actor_id != actor_id:
            return None
        if not run_transition_allowed(run.status, ResearchRunStatus.RUNNING):
            return RunControlResult(run, None, conflict=True)
        job_id = _enqueue_execution(self._jobs, run, actor)
        updated = self._store.cas_status(
            run_id,
            ResearchRunStatus.CREATED,
            ResearchRunStatus.RUNNING,
            field_updates={"started_at": datetime.now(tz=UTC)},
        )
        if updated is None:
            return RunControlResult(self._store.get_run(run_id) or run, None, conflict=True)
        return RunControlResult(updated, job_id, conflict=False)


class PauseResearchRun:
    """CAS running -> paused; the executor stops at the next step boundary."""

    def __init__(self, store: ResearchRunStore) -> None:
        """Wire the run store."""
        self._store = store

    def __call__(self, actor_id: uuid.UUID, run_id: uuid.UUID) -> RunControlResult | None:
        """Pause the run; None when absent, conflict=True on a CAS loss."""
        run = self._store.get_run(run_id)
        if run is None or run.actor_id != actor_id:
            return None
        if not run_transition_allowed(run.status, ResearchRunStatus.PAUSED):
            return RunControlResult(run, None, conflict=True)
        updated = self._store.cas_status(
            run_id, ResearchRunStatus.RUNNING, ResearchRunStatus.PAUSED
        )
        if updated is None:
            return RunControlResult(self._store.get_run(run_id) or run, None, conflict=True)
        return RunControlResult(updated, None, conflict=False)


class ResumeResearchRun:
    """CAS paused -> running and re-enqueue execution (revision-fresh idempotency)."""

    def __init__(self, store: ResearchRunStore, jobs: JobPorts) -> None:
        """Wire the run store and the job ports."""
        self._store = store
        self._jobs = jobs

    def __call__(
        self, actor_id: uuid.UUID, run_id: uuid.UUID, actor: InitiatingActor
    ) -> RunControlResult | None:
        """Resume the run; None when absent, conflict=True on a CAS loss."""
        run = self._store.get_run(run_id)
        if run is None or run.actor_id != actor_id:
            return None
        if not run_transition_allowed(run.status, ResearchRunStatus.RUNNING):
            return RunControlResult(run, None, conflict=True)
        job_id = _enqueue_execution(self._jobs, run, actor)
        updated = self._store.cas_status(
            run_id, ResearchRunStatus.PAUSED, ResearchRunStatus.RUNNING
        )
        if updated is None:
            return RunControlResult(self._store.get_run(run_id) or run, None, conflict=True)
        return RunControlResult(updated, job_id, conflict=False)


class CancelResearchRun:
    """CAS any non-terminal state -> cancelled; the orchestrator job is cancelled too."""

    def __init__(self, store: ResearchRunStore, jobs: JobPorts) -> None:
        """Wire the run store and the job ports."""
        self._store = store
        self._jobs = jobs

    def __call__(
        self, actor_id: uuid.UUID, run_id: uuid.UUID, *, reason: str = "user_requested"
    ) -> RunControlResult | None:
        """Cancel the run durably; None when absent, conflict=True on a CAS loss."""
        run = self._store.get_run(run_id)
        if run is None or run.actor_id != actor_id:
            return None
        if not run_transition_allowed(run.status, ResearchRunStatus.CANCELLED):
            return RunControlResult(run, None, conflict=True)
        updated = self._store.cas_status(
            run_id,
            run.status,
            ResearchRunStatus.CANCELLED,
            field_updates={"finished_at": datetime.now(tz=UTC)},
        )
        if updated is None:
            return RunControlResult(self._store.get_run(run_id) or run, None, conflict=True)
        self._cancel_execution(run)
        return RunControlResult(updated, None, conflict=False)

    def _cancel_execution(self, run: ResearchRunView) -> None:
        """Cancel the live orchestrator job so the executor stops cooperatively."""
        for job in self._jobs.repo.running_jobs(CapacityClass.RESEARCH_BROWSER.value):
            if job.kind == RESEARCH_EXECUTE_KIND and job.payload.get("run_id") == str(run.run_id):
                # A CAS loss here means a terminal writer (complete/fail) won
                # the race: the job already stopped, which is the desired end state.
                with contextlib.suppress(JobCasConflictError):
                    self._jobs.cancel(job.id, reason="run_cancelled")
                return
