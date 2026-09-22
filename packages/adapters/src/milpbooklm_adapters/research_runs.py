"""PostgreSQL implementation of the research run store (RSR-01b)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from milpbooklm_application.research import (
    EvidenceSnapshotView,
    ResearchRunView,
    ResearchStepView,
)
from milpbooklm_domain.research import (
    ResearchBudget,
    ResearchRunStatus,
    RunMode,
)

from milpbooklm_adapters.db.tables.research import (
    research_evidence_snapshots,
    research_run_steps,
    research_runs,
)


class PgResearchRunStore:
    """Durable research_runs/run_steps/evidence persistence with CAS updates."""

    def __init__(self, engine: sa.engine.Engine) -> None:
        """Bind the application-role database engine."""
        self._engine = engine

    def create_run(self, run: ResearchRunView, initial_snapshot: dict[str, object]) -> None:
        """Insert the run row with its frozen initial input snapshot."""
        with self._engine.begin() as connection:
            _ = connection.execute(
                sa.insert(research_runs).values(
                    id=run.run_id,
                    notebook_id=run.notebook_id,
                    initiated_by_user_id=run.actor_id,
                    goal=run.goal,
                    mode=run.mode.value,
                    budget=_budget_json(run.budget),
                    tools=sorted(run.tools),
                    approved_tools=sorted(run.approved_tools),
                    status=run.status.value,
                    initial_run_snapshot=initial_snapshot,
                    revision=run.revision,
                )
            )

    def get_run(self, run_id: uuid.UUID) -> ResearchRunView | None:
        """Load one run (logical view; None when absent)."""
        with self._engine.begin() as connection:
            row = (
                connection.execute(sa.select(research_runs).where(research_runs.c.id == run_id))
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return _run_view(row)

    def cas_status(
        self,
        run_id: uuid.UUID,
        expected: ResearchRunStatus,
        target: ResearchRunStatus,
        *,
        field_updates: dict[str, object] | None = None,
    ) -> ResearchRunView | None:
        """CAS the run status; None when the expected status no longer holds."""
        updates: dict[str, object] = {
            "status": target.value,
            "revision": research_runs.c.revision + 1,
        }
        if target in (
            ResearchRunStatus.SUCCEEDED,
            ResearchRunStatus.FAILED,
            ResearchRunStatus.CANCELLED,
        ):
            updates.setdefault("finished_at", datetime.now(tz=UTC))
        updates.update(field_updates or {})
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    sa.update(research_runs)
                    .where(
                        research_runs.c.id == run_id,
                        research_runs.c.status == expected.value,
                    )
                    .values(**updates)
                    .returning(research_runs)
                )
                .mappings()
                .one_or_none()
            )
        return _run_view(row) if row is not None else None

    def insert_step(self, step: ResearchStepView) -> None:
        """Append one step row (step_number uniqueness is per-run)."""
        with self._engine.begin() as connection:
            _ = connection.execute(
                sa.insert(research_run_steps).values(
                    id=step.step_id,
                    run_id=step.run_id,
                    step_number=step.step_number,
                    step_kind=step.step_kind,
                    tool_name=step.tool_name,
                    status=step.status,
                    input_manifest=step.input_manifest,
                    started_at=step.started_at,
                    finished_at=step.finished_at,
                )
            )

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
        updates: dict[str, object] = {
            "status": status,
            "finished_at": datetime.now(tz=UTC),
        }
        if tool_result is not None:
            updates["tool_result"] = tool_result
        if error_code is not None:
            updates["error_code"] = error_code
        if evidence_snapshot_id is not None:
            updates["evidence_snapshot_id"] = evidence_snapshot_id
        with self._engine.begin() as connection:
            _ = connection.execute(
                sa.update(research_run_steps)
                .where(research_run_steps.c.id == step_id)
                .values(**updates)
            )

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
        evidence_id = uuid.uuid4()
        with self._engine.begin() as connection:
            _ = connection.execute(
                sa.insert(research_evidence_snapshots).values(
                    id=evidence_id,
                    run_id=run_id,
                    origin_tool=origin_tool,
                    acquired_at=datetime.now(tz=UTC),
                    origin_locator=origin_locator,
                    content_sha256=content_sha256,
                    blob_id=blob_id,
                    locators=locators,
                    access_metadata=access_metadata,
                )
            )
            row = (
                connection.execute(
                    sa.select(research_evidence_snapshots).where(
                        research_evidence_snapshots.c.id == evidence_id
                    )
                )
                .mappings()
                .one()
            )
        return _evidence_view(row)

    def mark_promoted(self, evidence_id: uuid.UUID, source_version_id: uuid.UUID) -> bool:
        """One-time promotion link; False when already promoted (or absent)."""
        with self._engine.begin() as connection:
            result = connection.execute(
                sa.update(research_evidence_snapshots)
                .where(
                    research_evidence_snapshots.c.id == evidence_id,
                    research_evidence_snapshots.c.promoted_source_version_id.is_(None),
                )
                .values(promoted_source_version_id=source_version_id)
            )
        return result.rowcount == 1

    def list_steps(self, run_id: uuid.UUID) -> list[ResearchStepView]:
        """Return the run's steps in step_number order."""
        with self._engine.begin() as connection:
            rows = (
                connection.execute(
                    sa.select(research_run_steps)
                    .where(research_run_steps.c.run_id == run_id)
                    .order_by(research_run_steps.c.step_number)
                )
                .mappings()
                .all()
            )
        return [_step_view(row) for row in rows]

    def list_evidence(self, run_id: uuid.UUID) -> list[EvidenceSnapshotView]:
        """Return the run's immutable evidence records in append order."""
        with self._engine.begin() as connection:
            rows = (
                connection.execute(
                    sa.select(research_evidence_snapshots)
                    .where(research_evidence_snapshots.c.run_id == run_id)
                    .order_by(research_evidence_snapshots.c.acquired_at)
                )
                .mappings()
                .all()
            )
        return [_evidence_view(row) for row in rows]


def _run_view(row: Any) -> ResearchRunView:  # SQLAlchemy RowMapping boundary
    """Map one research_runs row onto the logical run view."""
    budget_row = row["budget"] or {}
    return ResearchRunView(
        run_id=row["id"],
        notebook_id=row["notebook_id"],
        actor_id=row["initiated_by_user_id"],
        goal=row["goal"],
        mode=RunMode(row["mode"]),
        status=ResearchRunStatus(row["status"]),
        tools=frozenset(row["tools"] or ()),
        approved_tools=frozenset(row["approved_tools"] or ()),
        budget=ResearchBudget(
            max_steps=int(budget_row.get("max_steps", 64)),
            max_tool_calls=int(budget_row.get("max_tool_calls", 48)),
            max_imports=int(budget_row.get("max_imports", 8)),
        ),
        error_code=row["error_code"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        revision=int(row["revision"] or 0),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _step_view(row: Any) -> ResearchStepView:  # SQLAlchemy RowMapping boundary
    """Map one research_run_steps row onto the logical step view."""
    return ResearchStepView(
        step_id=row["id"],
        run_id=row["run_id"],
        step_number=int(row["step_number"]),
        step_kind=row["step_kind"],
        tool_name=row["tool_name"],
        status=row["status"],
        input_manifest=row["input_manifest"],
        tool_result=row["tool_result"],
        error_code=row["error_code"],
        evidence_snapshot_id=row["evidence_snapshot_id"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
    )


def _evidence_view(row: Any) -> EvidenceSnapshotView:  # SQLAlchemy RowMapping boundary
    """Map one research_evidence_snapshots row onto the logical view."""
    return EvidenceSnapshotView(
        evidence_id=row["id"],
        run_id=row["run_id"],
        origin_tool=row["origin_tool"] or "",
        origin_locator=row["origin_locator"],
        content_sha256=row["content_sha256"],
        blob_id=row["blob_id"],
        locators=row["locators"],
        access_metadata=row["access_metadata"],
        promoted_source_version_id=row["promoted_source_version_id"],
        acquired_at=row["acquired_at"],
    )


def _budget_json(budget: ResearchBudget) -> dict[str, int]:
    return {
        "max_steps": budget.max_steps,
        "max_tool_calls": budget.max_tool_calls,
        "max_imports": budget.max_imports,
    }
