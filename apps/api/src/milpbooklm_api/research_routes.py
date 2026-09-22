"""Research run routes (RSR-01b): create/config, start, pause/resume/cancel, read."""

from __future__ import annotations

import uuid
from typing import Final

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from milpbooklm_application.job_actor import InitiatingActor
from milpbooklm_application.research import ResearchRunView, RunControlResult
from milpbooklm_domain.policy import PolicyAction
from milpbooklm_domain.research import ResearchBudget, RunMode
from milpbooklm_domain.telemetry import current_context
from pydantic import BaseModel, ConfigDict, Field

from .deps import ApiDeps, PrincipalDependency, ResearchRunDeps
from .security import Principal
from .source_http import authorize_notebook, problem

_HTTP_CREATED: Final = 201
_HTTP_ACCEPTED: Final = 202


class RunBudgetRequest(BaseModel):
    """Explicit per-run budget ceilings."""

    model_config = ConfigDict(frozen=True)

    max_steps: int = Field(default=64, ge=1, le=64)
    max_tool_calls: int = Field(default=48, ge=1, le=48)
    max_imports: int = Field(default=8, ge=0, le=8)


class CreateResearchRunRequest(BaseModel):
    """Validated run creation: goal, mode, explicit tools + approvals, budget."""

    model_config = ConfigDict(frozen=True)

    notebook_id: uuid.UUID
    goal: str = Field(min_length=1, max_length=4_000)
    mode: str = Field(default="source_discovery", pattern="^(source_discovery|deep_research)$")
    tools: tuple[str, ...] = Field(min_length=1)
    approved_tools: tuple[str, ...] = ()
    budget: RunBudgetRequest = RunBudgetRequest()


def _run_payload(run: ResearchRunView) -> dict[str, object]:
    """Serialize the authoritative run state without exposing storage paths."""
    return {
        "run_id": str(run.run_id),
        "notebook_id": str(run.notebook_id),
        "goal": run.goal,
        "mode": run.mode.value,
        "status": run.status.value,
        "tools": sorted(run.tools),
        "approved_tools": sorted(run.approved_tools),
        "budget": {
            "max_steps": run.budget.max_steps,
            "max_tool_calls": run.budget.max_tool_calls,
            "max_imports": run.budget.max_imports,
        },
        "error_code": run.error_code,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "revision": run.revision,
    }


def build_research_router(  # noqa: C901 - per-route handlers share one prefix
    deps: ApiDeps, principal_dependency: PrincipalDependency, research: ResearchRunDeps
) -> APIRouter:
    """Build the /api/v1/research-runs router over the wired use cases."""
    router = APIRouter(prefix="/api/v1/research-runs", tags=["research"])

    @router.post("", status_code=_HTTP_CREATED, response_model=None)
    def create(
        body: CreateResearchRunRequest, principal: Principal = Depends(principal_dependency)
    ) -> JSONResponse:
        """Create an explicitly configured run (frozen initial snapshot)."""
        denied = authorize_notebook(deps, principal, body.notebook_id, PolicyAction.RESEARCH_RUN)
        if denied is not None:
            return denied
        try:
            run = research.create(
                actor_id=principal.user.id,
                notebook_id=body.notebook_id,
                goal=body.goal,
                mode=RunMode(body.mode),
                tools=frozenset(body.tools),
                approved_tools=frozenset(body.approved_tools),
                budget=ResearchBudget(
                    max_steps=body.budget.max_steps,
                    max_tool_calls=body.budget.max_tool_calls,
                    max_imports=body.budget.max_imports,
                ),
            )
        except ValueError as exc:
            return problem("invalid_run_config", str(exc), 422)
        return JSONResponse(status_code=_HTTP_CREATED, content=_run_payload(run))

    @router.get("/{run_id}", response_model=None)
    def state(
        run_id: uuid.UUID, principal: Principal = Depends(principal_dependency)
    ) -> JSONResponse:
        """One run's authoritative state plus its append-only step ledger."""
        run = research.store.get_run(run_id)
        if run is None or run.actor_id != principal.user.id:
            return problem("run_not_found", "research run not found", 404)
        steps = research.store.list_steps(run_id)
        return JSONResponse(
            content={
                **_run_payload(run),
                "steps": [
                    {
                        "step_number": step.step_number,
                        "step_kind": step.step_kind,
                        "tool_name": step.tool_name,
                        "status": step.status,
                        "error_code": step.error_code,
                        "evidence_snapshot_id": (
                            str(step.evidence_snapshot_id) if step.evidence_snapshot_id else None
                        ),
                        "has_input_manifest": step.input_manifest is not None,
                    }
                    for step in steps
                ],
            }
        )

    @router.get("/{run_id}/evidence", response_model=None)
    def evidence(
        run_id: uuid.UUID, principal: Principal = Depends(principal_dependency)
    ) -> JSONResponse:
        """Return the run's immutable evidence records (metadata + hashes)."""
        run = research.store.get_run(run_id)
        if run is None or run.actor_id != principal.user.id:
            return problem("run_not_found", "research run not found", 404)
        rows = research.store.list_evidence(run_id)
        return JSONResponse(
            content={
                "evidence": [
                    {
                        "evidence_id": str(row.evidence_id),
                        "origin_tool": row.origin_tool,
                        "origin_locator": row.origin_locator,
                        "content_sha256": row.content_sha256,
                        "promoted_source_version_id": (
                            str(row.promoted_source_version_id)
                            if row.promoted_source_version_id
                            else None
                        ),
                        "acquired_at": row.acquired_at.isoformat(),
                    }
                    for row in rows
                ]
            }
        )

    @router.post("/{run_id}/start", status_code=_HTTP_ACCEPTED, response_model=None)
    def start(
        run_id: uuid.UUID, principal: Principal = Depends(principal_dependency)
    ) -> JSONResponse:
        """CAS created -> running and hand execution to the worker (202)."""
        result = research.start(principal.user.id, run_id, _actor(principal))
        return _control_response(result, "run_not_started")

    @router.post("/{run_id}/pause", response_model=None)
    def pause(
        run_id: uuid.UUID, principal: Principal = Depends(principal_dependency)
    ) -> JSONResponse:
        """CAS running -> paused; the executor stops at the next boundary."""
        result = research.pause(principal.user.id, run_id)
        return _control_response(result, "run_not_paused")

    @router.post("/{run_id}/resume", status_code=_HTTP_ACCEPTED, response_model=None)
    def resume(
        run_id: uuid.UUID, principal: Principal = Depends(principal_dependency)
    ) -> JSONResponse:
        """CAS paused -> running and re-enqueue execution (202)."""
        result = research.resume(principal.user.id, run_id, _actor(principal))
        return _control_response(result, "run_not_resumed")

    @router.post("/{run_id}/cancel", response_model=None)
    def cancel(
        run_id: uuid.UUID, principal: Principal = Depends(principal_dependency)
    ) -> JSONResponse:
        """Cancel the run durably (terminal; step/evidence ledger retained)."""
        result = research.cancel(principal.user.id, run_id)
        return _control_response(result, "run_not_cancelled")

    return router


def _control_response(result: RunControlResult | None, conflict_code: str) -> JSONResponse:
    """Map control results to HTTP: 404 absent, 409 conflict, else the run payload."""
    if result is None:
        return problem("run_not_found", "research run not found", 404)
    if result.conflict:
        return problem(
            conflict_code,
            f"run state conflict (current status: {result.run.status.value})",
            409,
        )
    if result.job_id is not None:
        return JSONResponse(
            status_code=_HTTP_ACCEPTED,
            content={**_run_payload(result.run), "job_id": result.job_id},
        )
    return JSONResponse(content=_run_payload(result.run))


def _actor(principal: Principal) -> InitiatingActor:
    """Build the job-initiating actor from the authenticated principal."""
    context = current_context()
    return InitiatingActor(
        user_id=principal.user.id,
        request_id=context.request_id if context is not None else None,
        trace_id=context.trace_id if context is not None else None,
    )
