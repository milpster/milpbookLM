"""Authenticated component-health surface (ok/degraded/down paths over fakes)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import sqlalchemy as sa
from fastapi.testclient import TestClient
from milpbooklm_adapters.provider_health import ProviderHealth
from milpbooklm_adapters.security.fakes import (
    InMemoryAuditLog,
    InMemoryNotebookCustodyStore,
    InMemoryNotebookReader,
    InMemoryUserRepository,
)
from milpbooklm_adapters.security.session_store import InMemorySessionTokenStore
from milpbooklm_api.composition import build_app
from milpbooklm_api.health_routes import (
    ComponentHealth,
    ComponentState,
    DeploymentHealth,
    ProbeOutcome,
    ServerComponents,
    ServerComponentStatus,
    probe_worker,
)
from milpbooklm_api.security import SecuritySettings
from starlette import status

ORIGIN = "https://testserver"
HEADERS = {"origin": ORIGIN}


class FakeClock:
    """Deterministic clock (unit-test time control)."""

    def __init__(self) -> None:
        self._now = datetime(2026, 9, 24, 12, 0, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> None:
        """Move the deterministic clock forward."""
        self._now = self._now + timedelta(seconds=seconds)


class FakeHasher:
    """Deterministic hasher (no real argon2 work in unit tests)."""

    def hash(self, password: str) -> str:
        return "h:" + password

    def verify(self, stored_hash: str, password: str) -> bool:
        return stored_hash == self.hash(password)

    def needs_rehash(self, stored_hash: str) -> bool:
        return False

    def dummy_verify(self, password: str) -> bool:
        return False


class _StubDeploymentHealth(DeploymentHealth):
    """Fixed probe outcomes (no engine round-trips)."""

    def __init__(self, components: tuple[ComponentHealth, ...]) -> None:
        super().__init__(sa.create_engine("sqlite://"), Path.cwd(), Path.cwd())
        self._fixed = components

    def probe(self) -> tuple[ComponentHealth, ...]:
        return self._fixed


_READY = ComponentState.READY
_DEGRADED = ComponentState.DEGRADED
_OK = ServerComponentStatus.OK
_DOWN = ServerComponentStatus.DOWN


def _ok_health() -> _StubDeploymentHealth:
    return _StubDeploymentHealth(
        (
            ComponentHealth(component="database", state=_READY),
            ComponentHealth(component="schema", state=_READY),
            ComponentHealth(component="blob", state=_READY),
            ComponentHealth(component="execution_prerequisites", state=_READY),
        )
    )


def make_client(
    health: DeploymentHealth | None,
    parts: ServerComponents | None,
) -> TestClient:
    """Build a wired TestClient over the fakes with the given health wiring."""
    clock = FakeClock()
    settings = SecuritySettings(secret_key="api-test-secret", base_url=ORIGIN)
    app = build_app(
        users=InMemoryUserRepository(),
        hasher=FakeHasher(),
        sessions=InMemorySessionTokenStore(secret_key=settings.secret_key, clock=clock),
        custody=InMemoryNotebookCustodyStore(),
        audit=InMemoryAuditLog(),
        notebooks=InMemoryNotebookReader(),
        settings=settings,
        clock=clock,
        health=health,
        server_components=parts,
    )
    return TestClient(app, base_url=ORIGIN)


def _login(client: TestClient) -> None:
    register = client.post(
        "/api/v1/auth/register",
        json={"email": "a@example.com", "display_name": "a", "password": "password-123"},
        headers=HEADERS,
    )
    assert register.status_code == status.HTTP_201_CREATED
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "password-123"},
        headers=HEADERS,
    )
    assert login.status_code == status.HTTP_200_OK


def _get_components(client: TestClient) -> dict[str, dict[str, str]]:
    response = client.get("/api/v1/health/components")
    assert response.status_code == status.HTTP_200_OK
    return {row["component"]: row for row in response.json()["components"]}


def test_components_requires_authentication() -> None:
    client = make_client(_ok_health(), None)
    response = client.get("/api/v1/health/components")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_components_reports_ok_rows() -> None:
    parts = ServerComponents(
        worker=lambda: ProbeOutcome(_OK, "last activity 2m ago"),
        chat_provider=lambda: ProbeOutcome(_OK, "last request 3m ago"),
        embedding_provider=lambda: ProbeOutcome(_OK, "last request 1m ago"),
    )
    client = make_client(_ok_health(), parts)
    _login(client)

    rows = _get_components(client)

    assert rows["database"] == {
        "component": "database",
        "status": "ok",
        "detail": "connected",
    }
    assert rows["blob_store"] == {
        "component": "blob_store",
        "status": "ok",
        "detail": "blob root writable",
    }
    assert rows["worker"] == {
        "component": "worker",
        "status": "ok",
        "detail": "last activity 2m ago",
    }
    assert rows["chat_provider"]["status"] == "ok"
    assert rows["embedding_provider"]["status"] == "ok"
    assert rows["search"] == {
        "component": "search",
        "status": "ok",
        "detail": "hybrid search (lexical + vector)",
    }


def test_components_reports_degraded_and_down_rows() -> None:
    health = _StubDeploymentHealth(
        (
            ComponentHealth(component="database", state=_DEGRADED, reason="database_unavailable"),
            ComponentHealth(component="schema", state=_DEGRADED, reason="schema_unavailable"),
            ComponentHealth(component="blob", state=_DEGRADED, reason="blob_root_unavailable"),
        )
    )
    parts = ServerComponents(
        worker=lambda: ProbeOutcome(ServerComponentStatus.DEGRADED, "2 queued job(s) unclaimed"),
        chat_provider=lambda: ProbeOutcome(
            ServerComponentStatus.DEGRADED, "last request failed (transport)"
        ),
        embedding_provider=lambda: ProbeOutcome(
            ServerComponentStatus.DEGRADED, "last request failed (transport)"
        ),
    )
    client = make_client(health, parts)
    _login(client)

    rows = _get_components(client)

    assert rows["database"]["status"] == "down"
    assert rows["database"]["detail"] == "database unreachable"
    assert rows["blob_store"]["status"] == "down"
    assert rows["worker"]["status"] == "degraded"
    assert rows["chat_provider"]["status"] == "degraded"
    assert rows["embedding_provider"]["status"] == "degraded"
    assert rows["search"]["status"] == "degraded"
    assert rows["search"]["detail"] == "unavailable (database down)"


def test_components_omits_unconfigured_embedding_and_derives_search() -> None:
    parts = ServerComponents(
        worker=lambda: ProbeOutcome(_OK, "last activity 1m ago"),
        chat_provider=lambda: ProbeOutcome(_OK, "last request 1m ago"),
        embedding_provider=None,
    )
    client = make_client(_ok_health(), parts)
    _login(client)

    rows = _get_components(client)

    assert "embedding_provider" not in rows
    assert rows["search"] == {
        "component": "search",
        "status": "ok",
        "detail": "lexical search",
    }


def test_components_fails_closed_when_not_wired() -> None:
    client = make_client(None, None)
    _login(client)

    rows = _get_components(client)

    assert rows["database"]["status"] == "down"
    assert rows["blob_store"]["status"] == "down"
    assert rows["worker"]["status"] == "degraded"
    assert rows["worker"]["detail"] == "not wired"
    assert rows["chat_provider"]["status"] == "degraded"
    assert "embedding_provider" not in rows
    assert rows["search"]["status"] == "degraded"


def test_probe_worker_reports_degraded_when_jobs_table_unreadable() -> None:
    engine = sa.create_engine("sqlite://")
    outcome = probe_worker(engine, datetime(2026, 9, 24, 12, 0, 0, tzinfo=UTC))
    assert outcome.status is ServerComponentStatus.DEGRADED
    assert outcome.detail == "liveness unknown (jobs table unreadable)"


def test_provider_health_snapshot_reports_latest_evidence() -> None:
    clock = FakeClock()
    health = ProviderHealth(clock)

    empty = health.snapshot()
    assert empty.healthy is False
    assert empty.detail == "no traffic observed"

    health.record_failure("transport")
    failed = health.snapshot()
    assert failed.healthy is False
    assert failed.detail == "last request failed (transport)"

    health.record_success()
    clock.advance(120)
    recovered = health.snapshot()
    assert recovered.healthy is True
    assert recovered.detail == "last request succeeded 2m ago"

    health.record_failure("response")
    again = health.snapshot()
    assert again.healthy is False
    assert again.detail == "last request failed (response)"
