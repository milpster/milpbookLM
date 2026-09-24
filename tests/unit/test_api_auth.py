"""API auth/security tests over the fakes (TestClient, https base for Secure cookies)."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

from fastapi.testclient import TestClient
from milpbooklm_adapters.security.fakes import (
    InMemoryAuditLog,
    InMemoryNotebookCustodyStore,
    InMemoryNotebookReader,
    InMemoryUserRepository,
)
from milpbooklm_adapters.security.session_store import InMemorySessionTokenStore
from milpbooklm_api.composition import build_app
from milpbooklm_api.deps import NoteDeps
from milpbooklm_api.security import ActiveUsersTracker, SecuritySettings
from milpbooklm_application.note_core import NoteRevisionView, NoteSnapshot, NoteView
from milpbooklm_application.note_lifecycle import (
    CreateNote,
    EditNote,
    PromoteNoteToSource,
    SaveResponseToNote,
    TransformNotes,
)
from milpbooklm_application.ports import NotebookView
from milpbooklm_domain.identity import User
from milpbooklm_domain.notes import NoteKind
from milpbooklm_domain.ownership import MembershipRole
from starlette import status

ORIGIN = "https://testserver"
HEADERS = {"origin": ORIGIN}


class FakeClock:
    """Deterministic clock (unit-test time control)."""

    def __init__(self) -> None:
        self._now = datetime(2026, 9, 19, 12, 0, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> None:
        """Move the deterministic clock forward (limiter window tests)."""
        self._now = self._now + timedelta(seconds=seconds)


class FakeHasher:
    """Deterministic hasher (no real argon2 work in unit tests)."""

    def _h(self, password: str) -> str:
        return "h:" + hashlib.sha256(password.encode()).hexdigest()

    def hash(self, password: str) -> str:
        return self._h(password)

    def verify(self, stored_hash: str, password: str) -> bool:
        return stored_hash == self._h(password)

    def needs_rehash(self, stored_hash: str) -> bool:
        return False

    def dummy_verify(self, password: str) -> bool:
        return self._h(password) == self._h("milpbooklm-dummy")


def _note_deps() -> NoteDeps:
    """Return a narrow note fake for route-level policy tests."""
    now = datetime(2026, 9, 19, 12, 0, 0, tzinfo=UTC)
    note_id = uuid.uuid4()
    revision_id = uuid.uuid4()
    snapshot = NoteSnapshot(
        note=NoteView(
            note_id=note_id,
            notebook_id=uuid.uuid4(),
            kind=NoteKind.USER,
            editable=True,
            title="Policy note",
            current_revision_id=revision_id,
            created_by_user_id=uuid.uuid4(),
            revision=1,
            etag="1",
            created_at=now,
            updated_at=now,
        ),
        revision=NoteRevisionView(
            revision_id=revision_id,
            note_id=note_id,
            revision_number=1,
            content={"blocks": [{"type": "paragraph", "text": "allowed"}]},
            content_sha256="sha256",
            author_user_id=uuid.uuid4(),
            provenance_refs=(),
            content_dependencies=(),
            created_at=now,
        ),
    )
    return NoteDeps(
        store=Mock(),
        create=Mock(spec=CreateNote, return_value=snapshot),
        edit=Mock(spec=EditNote),
        save_response=Mock(spec=SaveResponseToNote),
        transform=Mock(spec=TransformNotes),
        promote=Mock(spec=PromoteNoteToSource),
    )


def make_client(
    settings: SecuritySettings | None = None,
    seed_onboarding: Mock | None = None,
) -> TestClient:
    """Build a wired TestClient over the fakes (secure-cookie-friendly base URL)."""
    clock = FakeClock()
    resolved_settings = settings or SecuritySettings(secret_key="api-test-secret", base_url=ORIGIN)
    app = build_app(
        users=InMemoryUserRepository(),
        hasher=FakeHasher(),
        sessions=InMemorySessionTokenStore(secret_key=resolved_settings.secret_key, clock=clock),
        custody=InMemoryNotebookCustodyStore(),
        audit=InMemoryAuditLog(),
        notebooks=InMemoryNotebookReader(),
        settings=resolved_settings,
        clock=clock,
        notes=_note_deps(),
        seed_onboarding=seed_onboarding,
    )
    return TestClient(app, base_url=ORIGIN)


def register(client: TestClient, email: str, password: str = "password-123") -> str:
    """Register a user through the API; return the user id."""
    display = email.split("@", maxsplit=1)[0]
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "display_name": display, "password": password},
        headers=HEADERS,
    )
    assert response.status_code == status.HTTP_201_CREATED
    return response.json()["user_id"]


def login(client: TestClient, email: str, password: str = "password-123") -> dict[str, str]:
    """Log in through the API; return the response body (csrf_token, user_id)."""
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}, headers=HEADERS
    )
    assert response.status_code == status.HTTP_200_OK
    return response.json()


def test_login_sets_disciplined_cookie_and_csrf() -> None:
    client = make_client()
    register(client, "a@example.com")
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "password-123"},
        headers=HEADERS,
    )
    cookie = response.headers["set-cookie"]
    assert "mb_session=" in cookie
    assert "Secure" in cookie
    assert "HttpOnly" in cookie
    assert "samesite=lax" in cookie.lower()  # SameSite is case-insensitive (RFC 6265bis)
    assert "Path=/" in cookie
    body = response.json()
    assert body["csrf_token"]
    assert body["user_id"]


def test_me_with_session_and_without() -> None:
    client = make_client()
    register(client, "a@example.com")
    anonymous = client.get("/api/v1/auth/me")
    assert anonymous.status_code == status.HTTP_401_UNAUTHORIZED
    logged_in = login(client, "a@example.com")
    me = client.get("/api/v1/auth/me")
    assert me.status_code == status.HTTP_200_OK
    assert me.json()["email"] == "a@example.com"
    assert me.json()["installation_admin"] is False
    assert me.json()["csrf_token"] == logged_in["csrf_token"]


def test_instance_stats_counts_users_with_recent_authenticated_requests() -> None:
    client = make_client()
    anonymous = client.get("/api/v1/auth/instance-stats")
    assert anonymous.status_code == status.HTTP_401_UNAUTHORIZED

    register(client, "first@example.com")
    register(client, "second@example.com")
    register(client, "third@example.com")
    login(client, "first@example.com")
    # Sessions issued directly (no authenticated request) are NOT activity:
    # the counter measures request recency, never session existence.
    deps = client.app.state.deps
    second_id = deps.users.get_by_email("second@example.com").id
    deps.sessions.issue(user_id=second_id, ttl=timedelta(hours=1))

    response = client.get("/api/v1/auth/instance-stats")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"registered_users": 3, "active_users": 1}


def test_active_users_window_boundary_is_fifteen_minutes() -> None:
    clock = FakeClock()
    tracker = ActiveUsersTracker(clock)
    first = uuid.uuid4()
    second = uuid.uuid4()
    tracker.touch(first)
    clock.advance(timedelta(minutes=10).total_seconds())
    tracker.touch(second)

    assert tracker.count_active(now=clock.now()) == len({first, second})

    clock.advance(timedelta(minutes=5).total_seconds())
    assert tracker.count_active(now=clock.now()) == 1

    # The window boundary is strict: a touch 14m59s ago still counts, at
    # exactly 15m it does not (first is re-touched; second is long outside).
    tracker.touch(first)
    clock.advance(timedelta(minutes=14, seconds=59).total_seconds())
    assert tracker.count_active(now=clock.now()) == 1
    clock.advance(1)
    assert tracker.count_active(now=clock.now()) == 0


def test_register_seeds_onboarding_for_the_new_user() -> None:
    # Given
    seed_onboarding = Mock()
    client = make_client(seed_onboarding=seed_onboarding)

    # When
    user_id = register(client, "seeded@example.com")

    # Then
    seed_onboarding.assert_called_once_with(uuid.UUID(user_id))


def test_register_succeeds_when_onboarding_seed_fails() -> None:
    # Given
    seed_onboarding = Mock(side_effect=RuntimeError("seed unavailable"))
    client = make_client(seed_onboarding=seed_onboarding)

    # When
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "best-effort@example.com",
            "display_name": "best effort",
            "password": "password-123",
        },
        headers=HEADERS,
    )

    # Then
    assert response.status_code == status.HTTP_201_CREATED
    assert uuid.UUID(response.json()["user_id"])


def test_unsafe_without_origin_still_requires_csrf() -> None:
    # Given: a live session, but the request carries neither an Origin header
    # nor the CSRF token — origins are unrestricted, so only CSRF can reject it.
    client = make_client()
    register(client, "a@example.com")
    login(client, "a@example.com")

    # When
    response = client.post("/api/v1/auth/logout")

    # Then
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"detail": {"reason": "csrf_rejected"}}


def test_unsafe_without_csrf_token_rejected() -> None:
    client = make_client()
    register(client, "a@example.com")
    login(client, "a@example.com")
    response = client.post("/api/v1/auth/logout", headers=HEADERS)
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"detail": {"reason": "csrf_rejected"}}


def test_logout_with_csrf_revokes_session() -> None:
    client = make_client()
    register(client, "a@example.com")
    body = login(client, "a@example.com")
    response = client.post(
        "/api/v1/auth/logout", headers={**HEADERS, "x-csrf-token": body["csrf_token"]}
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert client.get("/api/v1/auth/me").status_code == status.HTTP_401_UNAUTHORIZED


def _client_with_notebooks() -> tuple[TestClient, str]:
    """A client seeded with an owner notebook and an admin without membership."""
    client = make_client()
    register(client, "owner@example.com")
    register(client, "admin@example.com")
    deps = client.app.state.deps
    notebook_id = uuid.uuid4()
    owner_id = deps.users.get_by_email("owner@example.com").id
    view = NotebookView(
        notebook_id=notebook_id,
        title="Atlas",
        custody_state="none",
        membership=MembershipRole.OWNER,
    )
    deps.notebooks.add_view(owner_id, view)
    return client, str(notebook_id)


def test_admin_has_no_content_access() -> None:
    client, notebook_id = _client_with_notebooks()
    deps = client.app.state.deps
    admin = deps.users.get_by_email("admin@example.com")
    # Promote to installation admin (the fake carries the flag on the User value).
    deps.users._users[admin.id] = User(
        id=admin.id,
        email=admin.email,
        display_name=admin.display_name,
        status=admin.status,
        installation_admin=True,
        created_at=admin.created_at,
    )
    login(client, "admin@example.com")
    assert client.get("/api/v1/notebooks").json() == []
    response = client.get(f"/api/v1/notebooks/{notebook_id}")
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"detail": {"reason": "deny:not_member"}}


def test_owner_allowed_viewer_denied_on_mutate() -> None:
    client, notebook_id = _client_with_notebooks()
    deps = client.app.state.deps
    body = login(client, "owner@example.com")
    assert client.get(f"/api/v1/notebooks/{notebook_id}").status_code == status.HTTP_200_OK
    created = client.post(
        f"/api/v1/notebooks/{notebook_id}/notes",
        json={
            "title": "Policy note",
            "content": {"blocks": [{"type": "paragraph", "text": "allowed"}]},
        },
        headers={**HEADERS, "x-csrf-token": body["csrf_token"]},
    )
    assert created.status_code == status.HTTP_201_CREATED

    client.cookies.clear()
    register(client, "viewer@example.com")
    viewer = deps.users.get_by_email("viewer@example.com")
    viewer_view = NotebookView(
        notebook_id=uuid.UUID(notebook_id),
        title="Atlas",
        custody_state="none",
        membership=MembershipRole.VIEWER,
    )
    deps.notebooks.add_view(viewer.id, viewer_view)
    client.cookies.clear()
    viewer_body = login(client, "viewer@example.com")
    denied = client.post(
        f"/api/v1/notebooks/{notebook_id}/notes",
        json={
            "title": "Denied note",
            "content": {"blocks": [{"type": "paragraph", "text": "denied"}]},
        },
        headers={**HEADERS, "x-csrf-token": viewer_body["csrf_token"]},
    )
    assert denied.status_code == status.HTTP_403_FORBIDDEN
    assert denied.json() == {"detail": {"reason": "deny:role"}}


def test_login_rate_limit_uniform_429() -> None:
    client = make_client(
        SecuritySettings(secret_key="api-test-secret", base_url=ORIGIN, login_max_attempts=2)
    )
    register(client, "a@example.com")
    first = client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "wrong"},
        headers=HEADERS,
    )
    second = client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "wrong"},
        headers=HEADERS,
    )
    third = client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "wrong"},
        headers=HEADERS,
    )
    assert first.status_code == status.HTTP_401_UNAUTHORIZED
    assert second.status_code == status.HTTP_401_UNAUTHORIZED
    assert third.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert third.json() == {"detail": {"reason": "rate_limited", "retry_after_seconds": 900}}
    assert third.headers["retry-after"] == "900"


def test_login_rate_limit_counts_successful_attempts() -> None:
    client = make_client(
        SecuritySettings(secret_key="api-test-secret", base_url=ORIGIN, login_max_attempts=2)
    )
    register(client, "a@example.com")
    login(client, "a@example.com")
    client.cookies.clear()
    login(client, "a@example.com")
    client.cookies.clear()

    denied = client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "password-123"},
        headers=HEADERS,
    )
    assert denied.status_code == status.HTTP_429_TOO_MANY_REQUESTS


def test_login_rate_limit_honors_configured_window_and_reports_retry_hint() -> None:
    login_window = timedelta(minutes=5)
    client = make_client(
        SecuritySettings(
            secret_key="api-test-secret",
            base_url=ORIGIN,
            login_max_attempts=2,
            login_window=login_window,
        )
    )
    register(client, "a@example.com")
    clock = client.app.state.deps.clock
    assert isinstance(clock, FakeClock)
    wrong = {"email": "a@example.com", "password": "wrong"}
    assert (
        client.post("/api/v1/auth/login", json=wrong, headers=HEADERS).status_code
        == status.HTTP_401_UNAUTHORIZED
    )
    assert (
        client.post("/api/v1/auth/login", json=wrong, headers=HEADERS).status_code
        == status.HTTP_401_UNAUTHORIZED
    )
    denied = client.post("/api/v1/auth/login", json=wrong, headers=HEADERS)
    assert denied.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert denied.json()["detail"]["reason"] == "rate_limited"
    assert denied.json()["detail"]["retry_after_seconds"] == int(login_window.total_seconds())
    assert denied.headers["retry-after"] == str(int(login_window.total_seconds()))
    clock.advance(login_window.total_seconds() + 1)
    after_window = client.post("/api/v1/auth/login", json=wrong, headers=HEADERS)
    assert after_window.status_code == status.HTTP_401_UNAUTHORIZED


def test_register_rate_limit_honors_configured_attempts_and_window() -> None:
    register_window = timedelta(minutes=7)
    client = make_client(
        SecuritySettings(
            secret_key="api-test-secret",
            base_url=ORIGIN,
            register_max_attempts=2,
            register_window=register_window,
        )
    )
    register(client, "a@example.com")
    register(client, "b@example.com")

    denied = client.post(
        "/api/v1/auth/register",
        json={"email": "c@example.com", "display_name": "c", "password": "password-123"},
        headers=HEADERS,
    )
    assert denied.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert denied.json() == {
        "detail": {
            "reason": "rate_limited",
            "retry_after_seconds": int(register_window.total_seconds()),
        }
    }
    assert denied.headers["retry-after"] == str(int(register_window.total_seconds()))

    clock = client.app.state.deps.clock
    assert isinstance(clock, FakeClock)
    clock.advance(register_window.total_seconds() + 1)
    register(client, "c@example.com")


def test_login_failure_uniform_unknown_vs_wrong_password() -> None:
    client = make_client()
    register(client, "a@example.com")
    unknown = client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@example.com", "password": "whatever"},
        headers=HEADERS,
    )
    wrong = client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "wrong"},
        headers=HEADERS,
    )
    assert unknown.status_code == status.HTTP_401_UNAUTHORIZED
    assert unknown.status_code == wrong.status_code
    assert unknown.json() == wrong.json() == {"detail": "invalid credentials"}
