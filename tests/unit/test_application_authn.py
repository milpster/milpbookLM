"""Application authn + custody use-case tests over the in-memory fakes."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from milpbooklm_adapters.security.fakes import (
    InMemoryAuditLog,
    InMemoryNotebookCustodyStore,
    InMemoryUserRepository,
)
from milpbooklm_adapters.security.session_store import (
    InMemorySessionTokenStore,
    derive_session_key,
    keyed_token_hash,
)
from milpbooklm_application.authn import (
    BootstrapAdmin,
    BootstrapError,
    LoginOutcome,
    LoginUser,
    LogoutUser,
    RegisterUser,
    RegistrationError,
    RotateSession,
)
from milpbooklm_application.custody_usecases import (
    CheckAccountDeletable,
    CustodyTransfer,
    DisableAccount,
    PermissionDeniedError,
)
from milpbooklm_domain.custody import CustodyPhase
from milpbooklm_domain.identity import UserStatus
from milpbooklm_domain.ownership import CustodyState

SECRET = "unit-test-secret"
TOKEN_HEX_LENGTH = 64  # 256-bit CSPRNG session token rendered as hex (ch17 §7)


class FakeClock:
    """Deterministic clock (unit-test time control)."""

    def __init__(self) -> None:
        self._now = datetime(2026, 9, 19, 12, 0, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta


class FakeHasher:
    """Deterministic hasher (no real argon2 work in unit tests)."""

    def __init__(self) -> None:
        self.work_burned = 0

    def _h(self, password: str) -> str:
        return "h:" + hashlib.sha256(password.encode()).hexdigest()

    def hash(self, password: str) -> str:
        return self._h(password)

    def verify(self, stored_hash: str, password: str) -> bool:
        self.work_burned += 1
        return stored_hash == self._h(password)

    def needs_rehash(self, stored_hash: str) -> bool:
        return False

    def dummy_verify(self, password: str) -> bool:
        self.work_burned += 1
        return self._h(password) == self._h("milpbooklm-dummy")


class Wired:
    """One wired identity stack over the fakes."""

    def __init__(self) -> None:
        self.clock = FakeClock()
        self.users = InMemoryUserRepository()
        self.hasher = FakeHasher()
        self.sessions = InMemorySessionTokenStore(secret_key=SECRET, clock=self.clock)
        self.audit = InMemoryAuditLog()
        self.custody = InMemoryNotebookCustodyStore()

    def register(self, email: str, password: str = "password-123") -> uuid.UUID:
        display = email.split("@", maxsplit=1)[0]
        return RegisterUser(self.users, self.hasher)(email, display, password)

    def login(self, email: str, password: str) -> LoginOutcome:
        return LoginUser(self.users, self.hasher, self.sessions, self.clock)(email, password)


def test_register_and_duplicate_rejected() -> None:
    wired = Wired()
    user_id = wired.register("a@example.com")
    assert wired.users.get(user_id) is not None
    with pytest.raises(RegistrationError):
        wired.register("A@example.com")


def test_register_rejects_short_password() -> None:
    wired = Wired()
    with pytest.raises(RegistrationError):
        wired.register("a@example.com", password="short")


def test_login_success_issues_session_storing_keyed_hash_only() -> None:
    wired = Wired()
    wired.register("a@example.com")
    outcome = wired.login("a@example.com", "password-123")
    assert outcome.succeeded
    assert outcome.session is not None
    token = outcome.session.token
    assert len(token) == TOKEN_HEX_LENGTH
    stored_hash = keyed_token_hash(derive_session_key(SECRET), token)
    rows = [r.token_hash for r in wired.sessions._rows.values()]
    assert stored_hash in rows
    assert token not in rows


def test_login_failure_is_uniform_and_burns_work() -> None:
    wired = Wired()
    wired.register("a@example.com")
    before = wired.hasher.work_burned
    unknown = wired.login("ghost@example.com", "whatever-123")
    wrong = wired.login("a@example.com", "wrong-password")
    assert unknown.succeeded is False
    assert unknown.failure == "invalid_credentials"
    assert wrong.succeeded is False
    assert wrong.failure == "invalid_credentials"
    assert wired.hasher.work_burned > before


def test_login_disabled_account_denied() -> None:
    wired = Wired()
    user_id = wired.register("a@example.com")
    wired.users.set_status(user_id, UserStatus.DISABLED)
    outcome = wired.login("a@example.com", "password-123")
    assert outcome.succeeded is False


def test_rotate_invalidates_old_token() -> None:
    wired = Wired()
    wired.register("a@example.com")
    outcome = wired.login("a@example.com", "password-123")
    old_token = outcome.session.token
    rotated = RotateSession(wired.sessions, wired.clock)(old_token)
    assert rotated is not None
    assert rotated.token != old_token
    assert wired.sessions.authenticate(old_token, now=wired.clock.now()) is None
    assert wired.sessions.authenticate(rotated.token, now=wired.clock.now()) is not None


def test_logout_revokes_session() -> None:
    wired = Wired()
    wired.register("a@example.com")
    token = wired.login("a@example.com", "password-123").session.token
    assert LogoutUser(wired.sessions, wired.clock)(token) is True
    assert wired.sessions.authenticate(token, now=wired.clock.now()) is None


def test_session_expiry_rejects_authenticate() -> None:
    wired = Wired()
    wired.register("a@example.com")
    token = wired.login("a@example.com", "password-123").session.token
    wired.clock.advance(timedelta(days=15))
    assert wired.sessions.authenticate(token, now=wired.clock.now()) is None


def test_bootstrap_is_one_time() -> None:
    wired = Wired()
    user_id = BootstrapAdmin(wired.users, wired.hasher)(
        "admin@example.com", "Admin", "long-enough-password"
    )
    assert wired.users.get(user_id).installation_admin is True
    with pytest.raises(BootstrapError):
        BootstrapAdmin(wired.users, wired.hasher)(
            "second@example.com", "Second", "long-enough-password"
        )


def _disable_stack() -> Wired:
    """A wired stack with an admin, a member and a sole-owned notebook."""
    wired = Wired()
    admin_id = BootstrapAdmin(wired.users, wired.hasher)(
        "admin@example.com", "Admin", "long-enough-password"
    )
    owner_id = wired.register("owner@example.com")
    notebook_id = uuid.uuid4()
    wired.custody.add_notebook(notebook_id, owner_id)
    wired._admin_id = admin_id
    wired._owner_id = owner_id
    wired._notebook_id = notebook_id
    return wired


def test_disable_account_revokes_sessions_and_locks_custody() -> None:
    wired = _disable_stack()
    wired.login("owner@example.com", "password-123")
    outcome = DisableAccount(wired.users, wired.sessions, wired.custody, wired.audit, wired.clock)(
        actor_id=wired._admin_id, user_id=wired._owner_id
    )
    assert outcome.revoked_sessions == 1
    assert outcome.locked_notebook_ids == (wired._notebook_id,)
    ownership, record = wired.custody.load_ownership(wired._notebook_id)
    assert record.phase is CustodyPhase.LOCKED
    assert ownership is not None
    assert ownership.custody_state is CustodyState.LOCKED_ADMIN_CUSTODY
    assert wired.login("owner@example.com", "password-123").succeeded is False


def test_non_admin_cannot_disable() -> None:
    wired = _disable_stack()
    with pytest.raises(PermissionDeniedError):
        DisableAccount(wired.users, wired.sessions, wired.custody, wired.audit, wired.clock)(
            actor_id=wired._owner_id, user_id=wired._owner_id
        )


def test_custody_transfer_moves_ownership_without_admin_membership() -> None:
    wired = _disable_stack()
    DisableAccount(wired.users, wired.sessions, wired.custody, wired.audit, wired.clock)(
        actor_id=wired._admin_id, user_id=wired._owner_id
    )
    recipient_id = wired.register("recipient@example.com")
    outcome = CustodyTransfer(wired.users, wired.custody, wired.audit, wired.clock)(
        actor_id=wired._admin_id,
        notebook_id=wired._notebook_id,
        new_owner_id=recipient_id,
    )
    assert outcome.new_owner_id == recipient_id
    ownership, record = wired.custody.load_ownership(wired._notebook_id)
    assert record.phase is CustodyPhase.NONE
    assert ownership is not None
    member_ids = frozenset(m.user_id for m in ownership.memberships)
    assert recipient_id in member_ids
    assert wired._admin_id not in member_ids
    assert wired._owner_id not in member_ids


def test_account_deletion_blocked_while_custody_locked() -> None:
    wired = _disable_stack()
    DisableAccount(wired.users, wired.sessions, wired.custody, wired.audit, wired.clock)(
        actor_id=wired._admin_id, user_id=wired._owner_id
    )
    gate = CheckAccountDeletable(wired.custody)(wired._owner_id)
    assert gate.deletable is False
    assert gate.blocking_notebook_ids == (wired._notebook_id,)
