"""PG-backed research run store: CAS, append-only evidence, one-time promotion."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from milpbooklm_adapters.db.connections import make_engine
from milpbooklm_adapters.research_runs import PgResearchRunStore
from milpbooklm_application.research import ResearchStepView
from milpbooklm_domain.research import (
    ResearchBudget,
    ResearchRunStatus,
)

from tests.domain.invariants._factories import Db

TOOLS = frozenset(
    {"web.search", "web.fetch", "browser.open", "source.import", "notebook.retrieve"}
)


def _scratch_dsn() -> str | None:
    socket_dir = Path("scratch/t13-smoke")
    if not (socket_dir / ".s.PGSQL.29521").exists():
        return None
    return (
        "postgresql://milpbooklm_app:milpbooklm_app@/milpbooklm_t13"
        f"?host={socket_dir.resolve()}&port=29521"
    )


@pytest.fixture(name="pg")
def _pg() -> Db | None:
    dsn = _scratch_dsn()
    if dsn is None:
        pytest.skip("live PostgreSQL acceptance stack is not running")
    return Db(dsn)


def _run_row(db: Db) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    actor = db.user()
    notebook = db.notebook(actor)
    run_id = uuid.uuid4()
    db.conn.execute(
        "INSERT INTO research_runs (id, notebook_id, initiated_by_user_id, goal, mode, "
        "budget, tools, approved_tools, status, initial_run_snapshot) "
        "VALUES (%s, %s, %s, 'goal', 'source_discovery', %s, %s, %s, 'created', '{}')",
        (
            run_id,
            notebook,
            actor,
            '{"max_steps": 8, "max_tool_calls": 4, "max_imports": 2}',
            json.dumps(sorted(TOOLS)),
            json.dumps(["source.import"]),
        ),
    )
    db.track("DELETE FROM research_runs WHERE id = %s", (run_id,))
    return run_id, actor, notebook


def test_cas_status_moves_only_along_legal_edges(pg: Db) -> None:
    run_id, _actor, _notebook = _run_row(pg)
    store = PgResearchRunStore(make_engine(_scratch_dsn().replace("postgresql://", "postgresql+psycopg://")))  # type: ignore[union-attr]

    started = store.cas_status(
        run_id, ResearchRunStatus.CREATED, ResearchRunStatus.RUNNING
    )
    assert started is not None
    assert started.status is ResearchRunStatus.RUNNING
    assert started.tools == TOOLS
    assert started.budget == ResearchBudget(max_steps=8, max_tool_calls=4, max_imports=2)

    # A second CAS from CREATED must lose: the row is RUNNING now.
    assert store.cas_status(run_id, ResearchRunStatus.CREATED, ResearchRunStatus.RUNNING) is None

    paused = store.cas_status(run_id, ResearchRunStatus.RUNNING, ResearchRunStatus.PAUSED)
    assert paused is not None
    assert paused.status is ResearchRunStatus.PAUSED
    resumed = store.cas_status(run_id, ResearchRunStatus.PAUSED, ResearchRunStatus.RUNNING)
    assert resumed is not None
    assert resumed.revision > paused.revision


def test_evidence_is_append_only_and_promotion_is_one_time(pg: Db) -> None:
    run_id, actor, notebook = _run_row(pg)
    source_id = pg.source(notebook, actor)
    promoted_version = pg.source_version(source_id, actor, status="activating")
    dsn = _scratch_dsn().replace("postgresql://", "postgresql+psycopg://")  # type: ignore[union-attr]
    store = PgResearchRunStore(make_engine(dsn))
    evidence = store.append_evidence(
        run_id,
        origin_tool="web.fetch",
        content_sha256="a" * 64,
        origin_locator="https://example.invalid/x",
    )

    engine = make_engine(dsn)
    with (
        engine.begin() as connection,
        pytest.raises(sa.exc.StatementError, match="immutable"),
    ):
        connection.execute(
            sa.text(
                "UPDATE research_evidence_snapshots SET content_sha256 = 'b'"
                " WHERE id = :id"
            ),
            {"id": evidence.evidence_id},
        )

    assert store.mark_promoted(evidence.evidence_id, promoted_version)
    assert not store.mark_promoted(evidence.evidence_id, promoted_version)
    rows = store.list_evidence(run_id)
    assert rows[0].promoted_source_version_id == promoted_version


def test_steps_carry_status_and_input_manifest_columns(pg: Db) -> None:
    run_id, _actor, _notebook = _run_row(pg)
    dsn = _scratch_dsn().replace("postgresql://", "postgresql+psycopg://")  # type: ignore[union-attr]
    store = PgResearchRunStore(make_engine(dsn))
    step_id = uuid.uuid4()
    store.insert_step(
        _step(run_id, step_id)
    )
    store.finish_step(
        step_id,
        status="succeeded",
        tool_result={"summary": "ok"},
        evidence_snapshot_id=None,
    )
    steps = store.list_steps(run_id)
    assert len(steps) == 1
    first = steps[0]
    assert first.status == "succeeded"
    assert first.tool_name == "web.search"
    assert first.input_manifest == {"goal": "goal"}
    assert first.tool_result == {"summary": "ok"}


def _step(run_id: uuid.UUID, step_id: uuid.UUID) -> ResearchStepView:

    return ResearchStepView(
        step_id=step_id,
        run_id=run_id,
        step_number=1,
        step_kind="search",
        tool_name="web.search",
        status="running",
        input_manifest={"goal": "goal"},
        tool_result=None,
        error_code=None,
        evidence_snapshot_id=None,
        started_at=datetime.now(tz=UTC),
        finished_at=None,
    )
