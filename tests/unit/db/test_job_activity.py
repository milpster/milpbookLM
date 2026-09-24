"""Server-wide job activity: identity-free honest feed over real job rows."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from milpbooklm_adapters.db.connections import make_engine
from milpbooklm_api.deps import ApiDeps
from milpbooklm_api.job_routes import JobActivity, build_job_router, job_activity
from milpbooklm_api.security import ActiveUsersTracker, Principal
from milpbooklm_application.job_usecases import JobPorts
from milpbooklm_domain.identity import User, UserStatus
from starlette import status

from tests.domain.invariants._factories import Db

# Per-run kind prefix so assertions survive live rows AND leaked rows of a
# previously failed run (this suite shares one database).
QA_KIND_PREFIX = f"qa.activity.{uuid.uuid4().hex[:8]}."
# Insertion ages under test, with a tolerance covering the insert->read delay.
INDEX_WAIT_SECONDS = 40
PARSE_AGE_SECONDS = 12
ACQUIRE_DONE_SECONDS = 94
AGE_TOLERANCE_SECONDS = 6


def _scratch_dsn() -> str | None:
    socket_dir = Path("scratch/t13-smoke")
    if not (socket_dir / ".s.PGSQL.29521").exists():
        return None
    return (
        "postgresql://milpbooklm_app:milpbooklm_app@/milpbooklm_t13"
        f"?host={socket_dir.resolve()}&port=29521"
    )


@pytest.fixture(name="pg")
def _pg() -> Db:
    dsn = _scratch_dsn()
    if dsn is None:
        pytest.skip("live PostgreSQL acceptance stack is not running")
    return Db(dsn)


def _api_deps() -> ApiDeps:
    return ApiDeps(
        users=Mock(),
        sessions=Mock(),
        register=Mock(),
        login=Mock(),
        rotate=Mock(),
        logout=Mock(),
        custody=Mock(),
        audit=Mock(),
        notebooks=Mock(),
        engine=Mock(),
        settings=Mock(),
        clock=Mock(),
        active_users=ActiveUsersTracker(Mock(**{"now.return_value": datetime.now(UTC)})),
        login_limiter=Mock(),
        register_limiter=Mock(),
    )


def _principal() -> Principal:
    user = User(
        id=uuid.uuid4(),
        email="reader@example.invalid",
        display_name="Reader",
        status=UserStatus.ACTIVE,
        installation_admin=False,
        created_at=datetime.now(UTC),
    )
    return Principal(user, uuid.uuid4(), "token", "csrf")


def _activity_client(activity: Callable[[], JobActivity] | None) -> TestClient:
    async def resolve_principal(_request: Request) -> Principal:
        return _principal()

    app = FastAPI()
    app.include_router(
        build_job_router(_api_deps(), resolve_principal, Mock(spec=JobPorts), activity)
    )
    return TestClient(app)


def _job_row(
    pg: Db,
    *,
    kind: str,
    job_status: str,
    requested_by: uuid.UUID,
    enqueued_at: datetime,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> uuid.UUID:
    job_id = uuid.uuid4()
    pg.conn.execute(
        "INSERT INTO jobs (id, queue, kind, payload, status, requested_by_user_id,"
        " enqueued_at, started_at, finished_at)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            job_id,
            "interactive_text",
            kind,
            json.dumps({}),
            job_status,
            requested_by,
            enqueued_at,
            started_at,
            finished_at,
        ),
    )
    pg.track("DELETE FROM jobs WHERE id = %s", (job_id,))
    return job_id


def _qa_slots(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [entry for entry in entries if str(entry["kind"]).startswith(QA_KIND_PREFIX)]


def test_activity_route_reports_server_wide_jobs_identity_free(pg: Db) -> None:
    # Given: jobs from two different actors, one per state, ages relative to now
    now = datetime.now(UTC)
    actor_a = pg.user()
    actor_b = pg.user()
    _job_row(
        pg,
        kind=f"{QA_KIND_PREFIX}parse",
        job_status="running",
        requested_by=actor_a,
        enqueued_at=now - timedelta(seconds=60),
        started_at=now - timedelta(seconds=12),
    )
    _job_row(
        pg,
        kind=f"{QA_KIND_PREFIX}index",
        job_status="queued",
        requested_by=actor_a,
        enqueued_at=now - timedelta(seconds=40),
    )
    _job_row(
        pg,
        kind=f"{QA_KIND_PREFIX}acquire",
        job_status="succeeded",
        requested_by=actor_b,
        enqueued_at=now - timedelta(seconds=300),
        started_at=now - timedelta(seconds=200),
        finished_at=now - timedelta(seconds=94),
    )
    dsn = _scratch_dsn()
    assert dsn is not None
    engine = make_engine(dsn.replace("postgresql://", "postgresql+psycopg://"))
    client = _activity_client(lambda: job_activity(engine, datetime.now(UTC)))

    # When
    response = client.get("/api/v1/jobs/activity")
    pg.close()

    # Then: honest counts and a live feed; ours is ordered oldest-waiting first
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["queued"] >= 1
    assert body["running"] >= 1
    active = _qa_slots(body["active"])
    assert [slot["state"] for slot in active] == ["queued", "running"]
    ages = {slot["kind"]: slot["age_seconds"] for slot in active}
    assert (
        INDEX_WAIT_SECONDS - AGE_TOLERANCE_SECONDS
        <= ages[f"{QA_KIND_PREFIX}index"]
        <= INDEX_WAIT_SECONDS + AGE_TOLERANCE_SECONDS
    )
    assert (
        PARSE_AGE_SECONDS - AGE_TOLERANCE_SECONDS
        <= ages[f"{QA_KIND_PREFIX}parse"]
        <= PARSE_AGE_SECONDS + AGE_TOLERANCE_SECONDS
    )
    recent = _qa_slots(body["recent"])
    assert [slot["state"] for slot in recent] == ["succeeded"]
    assert (
        ACQUIRE_DONE_SECONDS - AGE_TOLERANCE_SECONDS
        <= recent[0]["age_seconds"]
        <= ACQUIRE_DONE_SECONDS + AGE_TOLERANCE_SECONDS
    )

    # And: no actor identity survives into the payload (two different actors' jobs)
    serialized = json.dumps(body)
    assert str(actor_a) not in serialized
    assert str(actor_b) not in serialized
    assert "example.invalid" not in serialized
    for slot in [*body["active"], *body["recent"]]:
        assert set(slot) == {"kind", "state", "age_seconds"}


def test_activity_route_answers_503_when_unwired() -> None:
    client = _activity_client(None)

    response = client.get("/api/v1/jobs/activity")

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json()["code"] == "job_activity_unavailable"


def test_activity_route_requires_authentication() -> None:
    # A 401 (not 422) proves the static /activity path registered before /{job_id}.
    async def reject(_request: Request) -> Principal:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    app = FastAPI()
    app.include_router(build_job_router(_api_deps(), reject, Mock(spec=JobPorts), lambda: None))
    client = TestClient(app)

    response = client.get("/api/v1/jobs/activity")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
