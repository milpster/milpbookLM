"""
Drive one research run's steps under server-side tool authorization.

RSR-01b (guide/11 + guide/19, ARCH-11-001/005/008/010).

Prompt-injection posture, enforced structurally:

* tool outputs are UNTRUSTED DATA - they flow into planner context inside
  explicit delimiters and are hashed into immutable evidence, never executed;
* system/tool policy comes ONLY from the run's frozen configuration and this
  executor's authorization table - never from retrieved text;
* every planner proposal is schema-parsed (:func:`parse_action`) and then
  re-authorized against the run's tool set and recorded approvals
  (:func:`authorize_tool_call`): model output can never grant capability, so
  even a fully-compromised planner cannot escalate (denials are audited as
  ``tool.denied`` - the injection log);
* promotion happens ONLY when an approved ``source.import`` action reaches
  the normal ingestion path; the executor never writes source rows itself.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from milpbooklm_domain.research import (
    RESEARCH_TOOL_SURFACE,
    SIDE_EFFECT_TOOLS,
    ResearchRunStatus,
    ResearchTool,
    RunMode,
)

from .audit_actions import AuditAction
from .ports import AuditLog
from .research import (
    EvidenceSnapshotView,
    ResearchRunStore,
    ResearchRunView,
    ResearchStepView,
)
from .research_browser import (
    BrowserGestureCommand,
    BrowserSessionPort,
    BrowserUnavailableError,
)
from .research_browser_policy import browser_automation_denial
from .research_planner import (
    ActionParseError,
    BrowserInteractAction,
    BrowserObserveAction,
    BrowserOpenAction,
    FetchAction,
    FinishAction,
    ImportAction,
    PlannerAction,
    PlannerContext,
    ResearchPlanner,
    RetrieveAction,
    SearchAction,
    ToolTurn,
    parse_action,
)
from .retrieval import RetrievalCommand, RetrieveChunks
from .web_fetch import (
    AcquireWebSource,
    AcquireWebSourceCommand,
    FetchedWebContent,
    WebFetchCommand,
    WebFetchPort,
)
from .web_search import WebSearchCommand, WebSearchPort

logger = logging.getLogger(__name__)

_KIND_BY_TOOL: dict[str, str] = {
    ResearchTool.WEB_SEARCH.value: "search",
    ResearchTool.WEB_FETCH.value: "fetch",
    ResearchTool.BROWSER_OPEN.value: "browser",
    ResearchTool.BROWSER_OBSERVE.value: "browser",
    ResearchTool.BROWSER_INTERACT.value: "browser",
    ResearchTool.SOURCE_IMPORT.value: "import",
    ResearchTool.NOTEBOOK_RETRIEVE.value: "retrieve",
}

_PHASE_BY_TOOL: dict[str, str] = {
    ResearchTool.WEB_SEARCH.value: "searching",
    ResearchTool.WEB_FETCH.value: "reading",
    ResearchTool.SOURCE_IMPORT.value: "importing",
    ResearchTool.NOTEBOOK_RETRIEVE.value: "retrieving",
}

DENIED_NOT_IN_SURFACE = "tool_not_in_surface"
DENIED_NOT_ENABLED = "tool_not_enabled_on_run"
DENIED_NOT_APPROVED = "side_effect_not_approved"
DENIED_MALFORMED = "malformed_action"


def authorize_tool_call(run: ResearchRunView, tool: str) -> str | None:
    """
    Decide one proposed tool call from TRUSTED configuration only.

    Returns None when the call may proceed, else the stable denial reason.
    The seven-tool surface, the run's explicit tool set, and the recorded
    approvals are the only inputs - retrieved content has no vote.
    """
    if tool not in RESEARCH_TOOL_SURFACE:
        return DENIED_NOT_IN_SURFACE
    if tool not in run.tools:
        return DENIED_NOT_ENABLED
    if tool in SIDE_EFFECT_TOOLS and tool not in run.approved_tools:
        return DENIED_NOT_APPROVED
    return None


@dataclass(frozen=True, slots=True)
class PromotionResult:
    """Outcome of one source.import through the normal ingestion path."""

    source_id: uuid.UUID
    source_version_id: uuid.UUID
    job_id: uuid.UUID | None


class SourceImportPort(Protocol):
    """Promote fetched evidence via the NORMAL ingestion pipeline only."""

    async def import_fetched(
        self, *, actor_id: uuid.UUID, notebook_id: uuid.UUID, url: str, title: str
    ) -> PromotionResult:
        """Promote one curated fetch through ingestion."""
        ...


class IngestingSourceImport:
    """The only promotion path: an adapter over AcquireWebSource (ingestion)."""

    def __init__(self, acquire: AcquireWebSource) -> None:
        """Wire the normal web-acquisition use case (quarantine/blob/parse/index)."""
        self._acquire = acquire

    async def import_fetched(
        self, *, actor_id: uuid.UUID, notebook_id: uuid.UUID, url: str, title: str
    ) -> PromotionResult:
        """Fetch + acquire the curated URL through the normal pipeline."""
        view, _created, job_id = await self._acquire(
            AcquireWebSourceCommand(
                notebook_id=notebook_id,
                actor_id=actor_id,
                title=title,
                url=url,
            )
        )
        return PromotionResult(
            source_id=view.source_id,
            source_version_id=view.source_version_id,
            job_id=job_id,
        )


@dataclass(frozen=True, slots=True)
class ExecutorOutcome:
    """Terminal executor result (job result reference parts)."""

    run_status: ResearchRunStatus
    steps_executed: int
    evidence_appended: int


class ResearchRunExecutor:
    """Drive one run's planning/model/tool steps under authz + budget."""

    def __init__(
        self,
        *,
        store: ResearchRunStore,
        planners: dict[RunMode, ResearchPlanner],
        search: WebSearchPort,
        fetch: WebFetchPort,
        browser: BrowserSessionPort,
        imports: SourceImportPort,
        retrieval: RetrieveChunks,
        audit: AuditLog,
    ) -> None:
        """Wire the durable store, per-mode planners, tools, audit log."""
        self._store = store
        self._planners = planners
        self._search = search
        self._fetch = fetch
        self._browser = browser
        self._imports = imports
        self._retrieval = retrieval
        self._audit = audit

    async def execute(  # noqa: C901, PLR0911, PLR0912 - run control loop exits
        self,
        run_id: uuid.UUID,
        *,
        should_stop: Callable[[], bool],
        checkpoint: Callable[[dict[str, object]], None],
        progress: Callable[[str, float | None, str | None], None],
    ) -> ExecutorOutcome:
        """Run the loop until finish/pause/cancel/failure; resumable by design."""
        run = self._store.get_run(run_id)
        if run is None:
            raise LookupError(f"research run {run_id} not found")
        if run.status is not ResearchRunStatus.RUNNING:
            return ExecutorOutcome(run.status, 0, 0)
        planner = self._planners.get(run.mode)
        if planner is None:
            return self._fail(run, f"planner_unavailable_for_mode_{run.mode.value}")
        steps_executed = 0
        evidence_appended = 0
        tool_calls = self._count_tool_steps(run_id)
        while True:
            live = self._store.get_run(run_id)
            if live is None or live.status is not ResearchRunStatus.RUNNING:
                return ExecutorOutcome(
                    live.status if live else ResearchRunStatus.FAILED,
                    steps_executed,
                    evidence_appended,
                )
            if should_stop():
                # Pause/lease-loss boundary: durable state stays resumable.
                return ExecutorOutcome(ResearchRunStatus.RUNNING, steps_executed, evidence_appended)
            prior_steps = self._store.list_steps(run_id)
            if len(prior_steps) >= run.budget.max_steps:
                return self._fail(run, "budget_steps_exceeded")
            turns = self._turns_from(prior_steps)
            context = PlannerContext(
                run_id=str(run.run_id),
                notebook_id=str(run.notebook_id),
                goal=run.goal,
                mode=run.mode.value,
                tools=run.tools,
                turns=turns,
            )
            steps_executed += 1
            progress("planning", None, "deciding next action")
            step_id = self._begin_step(
                run,
                len(prior_steps) + 1,
                "plan",
                input_manifest=self._input_manifest(run, turns),
            )
            try:
                proposal = await planner.next_action(context)
                action = parse_action(proposal)
            except ActionParseError as exc:
                self._deny(run, DENIED_MALFORMED, tool="none", step_id=step_id, detail=str(exc))
                continue
            self._store.finish_step(step_id, status="succeeded")
            if isinstance(action, FinishAction):
                return self._succeed(run, action.summary)
            tool = _action_tool(action)
            denial = authorize_tool_call(run, tool)
            if denial is not None:
                self._deny(run, denial, tool=tool, step_id=None)
                continue
            if tool_calls >= run.budget.max_tool_calls:
                return self._fail(run, "budget_tool_calls_exceeded")
            if (
                tool == ResearchTool.SOURCE_IMPORT.value
                and self._count_promotions(run_id) >= run.budget.max_imports
            ):
                return self._fail(run, "budget_imports_exceeded")
            tool_calls += 1
            progress(_PHASE_BY_TOOL.get(tool, "executing tool"), None, tool)
            outcome = await self._dispatch(run, action)
            steps_executed += 1
            if outcome.evidence_id is not None:
                evidence_appended += 1
            checkpoint({"next_step": len(self._store.list_steps(run_id)) + 1})

    async def _dispatch(  # noqa: C901, PLR0911, PLR0912, PLR0915 - tool dispatch
        self, run: ResearchRunView, action: PlannerAction
    ) -> ToolTurn:
        """Execute one authorized tool call and append immutable evidence."""
        tool = _action_tool(action)
        step_number = len(self._store.list_steps(run.run_id)) + 1
        step_id = self._begin_step(run, step_number, _KIND_BY_TOOL[tool], tool_name=tool)
        try:
            match action:
                case SearchAction(query=query):
                    report = await self._search.search(WebSearchCommand(query=query))
                    body: dict[str, object] = {
                        "outcome": report.outcome.value,
                        "query": report.query,
                        "hits": [
                            {
                                "url": hit.url,
                                "title": hit.title,
                                "snippet": hit.snippet,
                                "engines": list(hit.engines),
                            }
                            for hit in report.hits
                        ],
                        "unresponsive_engines": list(report.unresponsive_engines),
                    }
                    summary = "\n".join(f"url={hit.url} title={hit.title}" for hit in report.hits)
                    evidence = self._append_evidence(run, tool, body, None)
                    self._store.finish_step(
                        step_id,
                        status="succeeded",
                        tool_result={"summary": summary},
                        evidence_snapshot_id=evidence.evidence_id,
                    )
                    return ToolTurn(tool, True, None, summary, str(evidence.evidence_id))
                case FetchAction(url=url):
                    try:
                        fetched = await self._fetch.fetch(WebFetchCommand(url=url))
                    except Exception as exc:
                        # The url rides in the step summary so the automation
                        # gate (guide/11: static fetch insufficient) can match
                        # it on resume as well as mid-run.
                        summary = f"fetch failed for {url}: {exc}"
                        self._store.finish_step(
                            step_id,
                            status="failed",
                            error_code=type(exc).__name__,
                            tool_result={"summary": summary},
                        )
                        return ToolTurn(tool, False, type(exc).__name__, summary)
                    evidence = self._append_fetched(run, fetched)
                    summary = (
                        f"fetch ok: {fetched.record.final_url} "
                        f"sha256={fetched.record.content_sha256}"
                    )
                    self._store.finish_step(
                        step_id,
                        status="succeeded",
                        tool_result={"summary": summary},
                        evidence_snapshot_id=evidence.evidence_id,
                    )
                    return ToolTurn(tool, True, None, summary, str(evidence.evidence_id))
                case BrowserOpenAction(url=url):
                    denial = browser_automation_denial(
                        run.approved_tools,
                        self._turns_from(self._store.list_steps(run.run_id)),
                        url,
                    )
                    if denial is not None:
                        self._deny(run, denial, tool=tool, step_id=step_id)
                        return ToolTurn(tool, False, denial, "browser automation not authorized")
                    page = await self._browser.open(url)
                    evidence = self._append_evidence(
                        run,
                        tool,
                        {
                            "url": page.url,
                            "title": page.title,
                            "requested_url": url,
                            "http_status": page.http_status,
                        },
                        page.url,
                    )
                    self._store.finish_step(
                        step_id, status="succeeded", evidence_snapshot_id=evidence.evidence_id
                    )
                    return ToolTurn(
                        tool, True, None, f"browser open: {page.url}", str(evidence.evidence_id)
                    )
                case BrowserObserveAction(focus=focus):
                    observation = await self._browser.observe(focus)
                    evidence = self._append_evidence(
                        run,
                        tool,
                        {
                            "url": observation.url,
                            "title": observation.title,
                            "focused": observation.focused_excerpt,
                        },
                        observation.url,
                    )
                    self._store.finish_step(
                        step_id, status="succeeded", evidence_snapshot_id=evidence.evidence_id
                    )
                    return ToolTurn(
                        tool, True, None, f"observed: {observation.url}", str(evidence.evidence_id)
                    )
                case BrowserInteractAction(gesture=gesture, selector=selector, value=value):
                    observation = await self._browser.interact(
                        BrowserGestureCommand(gesture=gesture, selector=selector, value=value)
                    )
                    evidence = self._append_evidence(
                        run,
                        tool,
                        {"gesture": gesture, "selector": selector, "url": observation.url},
                        observation.url,
                    )
                    self._store.finish_step(
                        step_id, status="succeeded", evidence_snapshot_id=evidence.evidence_id
                    )
                    return ToolTurn(
                        tool, True, None, f"interacted: {gesture}", str(evidence.evidence_id)
                    )
                case ImportAction(evidence_id=evidence_id, title=title):
                    target = self._evidence_by_id(run, uuid.UUID(evidence_id))
                    if target is None or target.origin_locator is None:
                        self._store.finish_step(
                            step_id, status="failed", error_code="import_target_missing"
                        )
                        return ToolTurn(
                            tool, False, "import_target_missing", "evidence not fetchable"
                        )
                    promotion = await self._imports.import_fetched(
                        actor_id=run.actor_id,
                        notebook_id=run.notebook_id,
                        url=target.origin_locator,
                        title=title,
                    )
                    self._store.mark_promoted(target.evidence_id, promotion.source_version_id)
                    summary = f"imported source_version={promotion.source_version_id}"
                    self._store.finish_step(
                        step_id, status="succeeded", tool_result={"summary": summary}
                    )
                    return ToolTurn(tool, True, None, summary)
                case RetrieveAction(query=query):
                    outcome = self._retrieval(
                        RetrievalCommand(
                            actor_user_id=run.actor_id,
                            notebook_id=run.notebook_id,
                            query=query,
                            language=None,
                            mode="lexical",
                            top_k=8,
                        )
                    )
                    body = {
                        "results": [
                            {
                                "chunk_id": str(chunk.row.chunk_id),
                                "source_title": chunk.row.source_title,
                                "text": chunk.row.text,
                            }
                            for chunk in outcome.results
                        ]
                    }
                    evidence = self._append_evidence(run, tool, body, None)
                    self._store.finish_step(
                        step_id, status="succeeded", evidence_snapshot_id=evidence.evidence_id
                    )
                    return ToolTurn(
                        tool,
                        True,
                        None,
                        f"retrieved {len(outcome.results)} chunks",
                        str(evidence.evidence_id),
                    )
                case unreachable:
                    raise AssertionError(f"unhandled action {unreachable!r}")
        except BrowserUnavailableError as exc:
            evidence = self._append_evidence(
                run, tool, {"refused": True, "code": exc.code, "detail": exc.detail}, None
            )
            self._store.finish_step(
                step_id,
                status="failed",
                error_code=exc.code,
                evidence_snapshot_id=evidence.evidence_id,
            )
            return ToolTurn(tool, False, exc.code, str(exc), str(evidence.evidence_id))
        except Exception as exc:
            self._store.finish_step(step_id, status="failed", error_code=type(exc).__name__)
            return ToolTurn(tool, False, type(exc).__name__, f"tool failure: {exc}")

    def _begin_step(
        self,
        run: ResearchRunView,
        step_number: int,
        kind: str,
        *,
        tool_name: str | None = None,
        input_manifest: dict[str, object] | None = None,
    ) -> uuid.UUID:
        """Insert one step row in the running state and return its id."""
        step_id = uuid.uuid4()
        self._store.insert_step(
            ResearchStepView(
                step_id=step_id,
                run_id=run.run_id,
                step_number=step_number,
                step_kind=kind,
                tool_name=tool_name,
                status="running",
                input_manifest=input_manifest,
                tool_result=None,
                error_code=None,
                evidence_snapshot_id=None,
                started_at=datetime.now(tz=UTC),
                finished_at=None,
            )
        )
        return step_id

    def _input_manifest(
        self, run: ResearchRunView, turns: tuple[ToolTurn, ...]
    ) -> dict[str, object]:
        """Build the child input manifest for one planning/model step (ARCH-11-001)."""
        return {
            "goal": run.goal,
            "mode": run.mode.value,
            "tools": sorted(run.tools),
            "approved_tools": sorted(run.approved_tools),
            "budget": {
                "max_steps": run.budget.max_steps,
                "max_tool_calls": run.budget.max_tool_calls,
                "max_imports": run.budget.max_imports,
            },
            "prior_tool_turns": [
                {
                    "tool": turn.tool,
                    "ok": turn.ok,
                    "evidence_id": turn.evidence_id,
                    "refusal_code": turn.refusal_code,
                }
                for turn in turns
            ],
        }

    def _append_evidence(
        self,
        run: ResearchRunView,
        tool: str,
        body: dict[str, object],
        origin_locator: str | None,
    ) -> EvidenceSnapshotView:
        """Hash + append one immutable evidence record for a tool output."""
        payload = json.dumps(body, sort_keys=True, ensure_ascii=True).encode()
        return self._store.append_evidence(
            run.run_id,
            origin_tool=tool,
            content_sha256=hashlib.sha256(payload).hexdigest(),
            origin_locator=origin_locator,
            access_metadata={"content_bytes": len(payload)},
        )

    def _append_fetched(
        self, run: ResearchRunView, fetched: FetchedWebContent
    ) -> EvidenceSnapshotView:
        """Record a web.fetch outcome with its full retrieval record."""
        locators: dict[str, object] = {
            "requested_url": fetched.record.requested_url,
            "final_url": fetched.record.final_url,
            "redirect_chain": list(fetched.record.redirect_chain),
        }
        access_metadata: dict[str, object] = {
            "captured_at": fetched.record.captured_at,
            "status_code": fetched.record.status_code,
            "content_type": fetched.record.content_type,
            "size_bytes": fetched.record.size_bytes,
            "headers": [[name, value] for name, value in fetched.headers],
        }
        return self._store.append_evidence(
            run.run_id,
            origin_tool=ResearchTool.WEB_FETCH.value,
            content_sha256=fetched.record.content_sha256,
            origin_locator=fetched.record.final_url,
            locators=locators,
            access_metadata=access_metadata,
        )

    def _evidence_by_id(
        self, run: ResearchRunView, evidence_id: uuid.UUID
    ) -> EvidenceSnapshotView | None:
        """Load one evidence record of this run (None when absent)."""
        for evidence in self._store.list_evidence(run.run_id):
            if evidence.evidence_id == evidence_id:
                return evidence
        return None

    def _count_tool_steps(self, run_id: uuid.UUID) -> int:
        """Count prior tool steps (resume accounting for the tool budget)."""
        return sum(1 for step in self._store.list_steps(run_id) if step.tool_name is not None)

    def _count_promotions(self, run_id: uuid.UUID) -> int:
        """Count already-promoted evidence records (import budget)."""
        return sum(
            1
            for evidence in self._store.list_evidence(run_id)
            if evidence.promoted_source_version_id is not None
        )

    def _turns_from(self, steps: list[ResearchStepView]) -> tuple[ToolTurn, ...]:
        """Rebuild planner-visible turns from durable steps (resume path)."""
        return tuple(
            ToolTurn(
                tool=step.tool_name or "none",
                ok=step.status == "succeeded",
                refusal_code=step.error_code,
                summary=str((step.tool_result or {}).get("summary", "")),
                evidence_id=(str(step.evidence_snapshot_id) if step.evidence_snapshot_id else None),
            )
            for step in steps
            if step.tool_name is not None
        )

    def _deny(
        self,
        run: ResearchRunView,
        reason: str,
        *,
        tool: str,
        step_id: uuid.UUID | None,
        detail: str | None = None,
    ) -> None:
        """Record a server-side denial: failed step + audited injection log."""
        logger.warning("research tool denied: run=%s tool=%s reason=%s", run.run_id, tool, reason)
        details = {"tool": tool, "reason": reason}
        if detail is not None:
            details["detail"] = detail
        self._audit.record(
            actor_id=run.actor_id,
            action=AuditAction.TOOL_DENIED.value,
            subject_kind="research_run",
            subject_id=run.run_id,
            details=details,
        )
        if step_id is not None:
            self._store.finish_step(step_id, status="failed", error_code=f"denied:{reason}")

    def _succeed(self, run: ResearchRunView, summary: str) -> ExecutorOutcome:
        """Publish the succeeded terminal state with candidate imports."""
        evidence_rows = self._store.list_evidence(run.run_id)
        promoted = [
            {
                "evidence_id": str(evidence.evidence_id),
                "source_version_id": str(evidence.promoted_source_version_id),
                "origin_locator": evidence.origin_locator,
            }
            for evidence in evidence_rows
            if evidence.promoted_source_version_id is not None
        ]
        self._store.cas_status(
            run.run_id,
            ResearchRunStatus.RUNNING,
            ResearchRunStatus.SUCCEEDED,
            field_updates={
                "finished_at": datetime.now(tz=UTC),
                "candidate_imports": promoted,
                "plan": {"final_summary": summary},
            },
        )
        return ExecutorOutcome(
            ResearchRunStatus.SUCCEEDED,
            len(self._store.list_steps(run.run_id)),
            len(evidence_rows),
        )

    def _fail(self, run: ResearchRunView, error_code: str) -> ExecutorOutcome:
        """Publish the failed terminal state with its stable error code."""
        self._store.cas_status(
            run.run_id,
            ResearchRunStatus.RUNNING,
            ResearchRunStatus.FAILED,
            field_updates={
                "finished_at": datetime.now(tz=UTC),
                "error_code": error_code,
            },
        )
        return ExecutorOutcome(ResearchRunStatus.FAILED, 0, 0)


def _action_tool(action: PlannerAction) -> str:  # noqa: PLR0911 - one arm per action
    """Map a parsed action to its tool name (finish is the pseudo name)."""
    match action:
        case SearchAction():
            return ResearchTool.WEB_SEARCH.value
        case FetchAction():
            return ResearchTool.WEB_FETCH.value
        case BrowserOpenAction():
            return ResearchTool.BROWSER_OPEN.value
        case BrowserObserveAction():
            return ResearchTool.BROWSER_OBSERVE.value
        case BrowserInteractAction():
            return ResearchTool.BROWSER_INTERACT.value
        case ImportAction():
            return ResearchTool.SOURCE_IMPORT.value
        case RetrieveAction():
            return ResearchTool.NOTEBOOK_RETRIEVE.value
        case FinishAction():
            return "finish"
        case unreachable:
            raise AssertionError(f"unhandled action {unreachable!r}")
