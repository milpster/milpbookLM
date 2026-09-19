"""
Authentication use cases: register, login, rotate, logout, one-time bootstrap.

Enumeration resistance lives here at the outcome level: a login failure is a single
uniform outcome regardless of whether the email exists or the password is wrong, so
the transport layer (API) can emit one identical response for both. Login rotates the
session identifier on authentication (ch17 §7); the prior session for that user is
revoked by rotation-at-login only for the presented token, other devices stay valid.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import timedelta

from .ports import (
    Clock,
    IssuedSessionData,
    PasswordHasher,
    SessionTokenStore,
    UserRepository,
)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

DEFAULT_SESSION_TTL = timedelta(days=14)
MIN_PASSWORD_LENGTH = 8
MIN_ADMIN_PASSWORD_LENGTH = 12


class RegistrationError(ValueError):
    """The email is missing/invalid or already taken (the API maps this to 409)."""


class BootstrapError(RuntimeError):
    """The one-time bootstrap window has closed (an account already exists)."""


@dataclass(frozen=True, slots=True)
class LoginOutcome:
    """Uniform login result: on failure ``session`` is None and ``failure`` is set."""

    succeeded: bool
    session: IssuedSessionData | None = None
    user_id: uuid.UUID | None = None
    failure: str | None = None


class RegisterUser:
    """Create a local account with a calibrated Argon2id hash."""

    def __init__(self, users: UserRepository, hasher: PasswordHasher) -> None:
        """Wire the ports the use case needs."""
        self._users = users
        self._hasher = hasher

    def __call__(self, email: str, display_name: str, password: str) -> uuid.UUID:
        """Register and return the new user id; raise RegistrationError otherwise."""
        email = email.strip().lower()
        if not EMAIL_RE.fullmatch(email):
            raise RegistrationError("email is invalid")
        if not display_name.strip():
            raise RegistrationError("display name is required")
        if len(password) < MIN_PASSWORD_LENGTH:
            raise RegistrationError("password is too short")
        if self._users.get_by_email(email) is not None:
            raise RegistrationError("email is already registered")
        hashed = self._hasher.hash(password)
        return self._users.create(
            email=email, display_name=display_name.strip(), password_hash=hashed
        ).id


class LoginUser:
    """Authenticate by email/password; issue a rotated session on success."""

    def __init__(
        self,
        users: UserRepository,
        hasher: PasswordHasher,
        sessions: SessionTokenStore,
        clock: Clock,
        session_ttl: timedelta = DEFAULT_SESSION_TTL,
    ) -> None:
        """Wire the ports the use case needs."""
        self._users = users
        self._hasher = hasher
        self._sessions = sessions
        self._clock = clock
        self._session_ttl = session_ttl

    def __call__(self, email: str, password: str) -> LoginOutcome:
        """Return a uniform LoginOutcome; failures never distinguish the cause."""
        record = self._users.get_record(email.strip().lower())
        if record is None:
            # Burn one full hash of work so timing does not reveal account existence.
            self._hasher.dummy_verify(password)
            return LoginOutcome(succeeded=False, failure="invalid_credentials")
        user = record.user
        if not user.enabled:
            # Disabled accounts fail identically to bad credentials (AD-022 immediate).
            self._hasher.dummy_verify(password)
            return LoginOutcome(succeeded=False, failure="invalid_credentials")
        if not self._hasher.verify(record.password_hash, password):
            return LoginOutcome(succeeded=False, failure="invalid_credentials")
        session = self._sessions.issue(user_id=user.id, ttl=self._session_ttl)
        return LoginOutcome(succeeded=True, session=session, user_id=user.id)


class RotateSession:
    """Replace a live session token (privilege change) and revoke the old one."""

    def __init__(
        self,
        sessions: SessionTokenStore,
        clock: Clock,
        session_ttl: timedelta = DEFAULT_SESSION_TTL,
    ) -> None:
        """Wire the ports the use case needs."""
        self._sessions = sessions
        self._clock = clock
        self._session_ttl = session_ttl

    def __call__(self, old_token: str) -> IssuedSessionData | None:
        """Rotate the token; return None when the presented token is not live."""
        resolved = self._sessions.authenticate(old_token, now=self._clock.now())
        if resolved is None:
            return None
        old_session_id, _ = resolved
        return self._sessions.rotate(old_session_id, ttl=self._session_ttl)


class LogoutUser:
    """Revoke the presented session token."""

    def __init__(self, sessions: SessionTokenStore, clock: Clock) -> None:
        """Wire the ports the use case needs."""
        self._sessions = sessions
        self._clock = clock

    def __call__(self, token: str) -> bool:
        """Revoke the session; return True when a live session was revoked."""
        resolved = self._sessions.authenticate(token, now=self._clock.now())
        if resolved is None:
            return False
        self._sessions.revoke(resolved[0])
        return True


class BootstrapAdmin:
    """One-time first-administrator creation (no universal/default password)."""

    def __init__(self, users: UserRepository, hasher: PasswordHasher) -> None:
        """Wire the ports the use case needs."""
        self._users = users
        self._hasher = hasher

    def __call__(self, email: str, display_name: str, password: str) -> uuid.UUID:
        """Create the single installation administrator; raise when the window closed."""
        if self._users.count() != 0:
            raise BootstrapError("installation already bootstrapped")
        email = email.strip().lower()
        if not EMAIL_RE.fullmatch(email):
            raise RegistrationError("email is invalid")
        if not display_name.strip():
            raise RegistrationError("display name is required")
        if len(password) < MIN_ADMIN_PASSWORD_LENGTH:
            raise RegistrationError("administrator password is too short")
        hashed = self._hasher.hash(password)
        return self._users.create(
            email=email,
            display_name=display_name.strip(),
            password_hash=hashed,
            installation_admin=True,
        ).id
