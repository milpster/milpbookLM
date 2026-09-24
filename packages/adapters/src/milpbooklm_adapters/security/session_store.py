"""
Session token storage: 256-bit CSPRNG opaque tokens, keyed-hash-only persistence.

The sessions.token_hash column stores ONLY a keyed HMAC-SHA256 digest (ch17 §7);
the plaintext token exists only in the cookie and in the ephemeral
IssuedSessionData value object. CSRF tokens are derived statelessly (no schema
column): a second keyed HMAC over the session token, so validation never needs
a storage round-trip.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

import sqlalchemy as sa
from milpbooklm_application.ports import Clock, IssuedSessionData

from milpbooklm_adapters.db.tables.identity import sessions

# 256-bit opaque session tokens (ch17 §7).
TOKEN_BYTES = 32

_SESSION_KEY_CONTEXT = b"milpbooklm/session/v1"
_CSRF_KEY_CONTEXT = b"milpbooklm/csrf/v1"


def derive_session_key(secret_key: str) -> bytes:
    """Derive the keyed-hash key for session tokens from the installation secret."""
    return hmac.new(secret_key.encode(), _SESSION_KEY_CONTEXT, hashlib.sha256).digest()


def keyed_token_hash(key: bytes, token: str) -> str:
    """Return the only storable form of a session token: its keyed HMAC-SHA256 hex."""
    return hmac.new(key, token.encode(), hashlib.sha256).hexdigest()


def new_session_token() -> str:
    """Mint a fresh 256-bit CSPRNG opaque token (64 hex chars)."""
    return secrets.token_hex(TOKEN_BYTES)


def derive_csrf_token(secret_key: str, session_token: str) -> str:
    """Derive the CSRF token for a live session (stateless; no storage column)."""
    key = hmac.new(secret_key.encode(), _CSRF_KEY_CONTEXT, hashlib.sha256).digest()
    digest = hmac.new(key, session_token.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii")


@dataclass(frozen=True, slots=True)
class _SessionRow:
    """Internal stored row: keyed hash + metadata, never the plaintext token."""

    session_id: uuid.UUID
    user_id: uuid.UUID
    token_hash: str
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    user_agent: str | None = None


class PgSessionTokenStore:
    """The sessions table adapter: keyed-hash-only session storage (ch17 §7)."""

    def __init__(self, engine: sa.engine.Engine, *, secret_key: str, clock: Clock) -> None:
        """Wire the engine, the installation secret and the clock."""
        self._engine = engine
        self._key = derive_session_key(secret_key)
        self._clock = clock

    def issue(
        self, *, user_id: uuid.UUID, ttl: timedelta, user_agent: str | None = None
    ) -> IssuedSessionData:
        """Issue a new session for the user and persist its keyed hash + metadata."""
        token = new_session_token()
        now = self._clock.now()
        with self._engine.begin() as conn:
            row = conn.execute(
                sa.insert(sessions)
                .values(
                    user_id=user_id,
                    token_hash=keyed_token_hash(self._key, token),
                    user_agent=user_agent,
                    expires_at=now + ttl,
                )
                .returning(sessions.c.id)
            ).one()
        return IssuedSessionData(
            session_id=row.id,
            token=token,
            created_at=now,
            expires_at=now + ttl,
        )

    def authenticate(self, token: str, *, now: datetime) -> tuple[uuid.UUID, uuid.UUID] | None:
        """Resolve a token to (session_id, user_id), or None (unknown/revoked/expired)."""
        digest = keyed_token_hash(self._key, token)
        with self._engine.begin() as conn:
            row = conn.execute(
                sa.select(
                    sessions.c.id, sessions.c.user_id, sessions.c.expires_at, sessions.c.revoked_at
                ).where(sessions.c.token_hash == digest)
            ).first()
        if row is None or row.revoked_at is not None or row.expires_at <= now:
            return None
        return (row.id, row.user_id)

    def revoke(self, session_id: uuid.UUID) -> None:
        """Revoke one session (idempotent)."""
        with self._engine.begin() as conn:
            conn.execute(
                sa.update(sessions)
                .where(sessions.c.id == session_id, sessions.c.revoked_at.is_(None))
                .values(revoked_at=self._clock.now())
            )

    def revoke_all_for_user(self, user_id: uuid.UUID) -> int:
        """Revoke every live session of the user; return how many were revoked."""
        with self._engine.begin() as conn:
            result = conn.execute(
                sa.update(sessions)
                .where(sessions.c.user_id == user_id, sessions.c.revoked_at.is_(None))
                .values(revoked_at=self._clock.now())
            )
        return result.rowcount

    def rotate(self, old_session_id: uuid.UUID, *, ttl: timedelta) -> IssuedSessionData:
        """Replace a live session with a fresh token (rotation on privilege change)."""
        with self._engine.begin() as conn:
            user_id = conn.execute(
                sa.select(sessions.c.user_id).where(sessions.c.id == old_session_id)
            ).scalar_one()
            token = new_session_token()
            now = self._clock.now()
            row = conn.execute(
                sa.insert(sessions)
                .values(
                    user_id=user_id,
                    token_hash=keyed_token_hash(self._key, token),
                    expires_at=now + ttl,
                )
                .returning(sessions.c.id)
            ).one()
            conn.execute(
                sa.update(sessions)
                .where(sessions.c.id == old_session_id, sessions.c.revoked_at.is_(None))
                .values(revoked_at=now)
            )
        return IssuedSessionData(
            session_id=row.id, token=token, created_at=now, expires_at=now + ttl
        )


class InMemorySessionTokenStore:
    """Deterministic fake session store (same keyed-hash discipline, no I/O)."""

    def __init__(self, *, secret_key: str, clock: Clock) -> None:
        """Wire the secret and the clock."""
        self._key = derive_session_key(secret_key)
        self._clock = clock
        self._rows: dict[uuid.UUID, _SessionRow] = {}
        self._next_id = 1

    def _new_id(self) -> uuid.UUID:
        """Mint the next fake session id (deterministic order)."""
        session_id = uuid.uuid5(uuid.NAMESPACE_URL, f"milpbooklm/session/{self._next_id}")
        self._next_id += 1
        return session_id

    def issue(
        self, *, user_id: uuid.UUID, ttl: timedelta, user_agent: str | None = None
    ) -> IssuedSessionData:
        """Issue a new session for the user (in memory)."""
        token = new_session_token()
        now = self._clock.now()
        session_id = self._new_id()
        self._rows[session_id] = _SessionRow(
            session_id=session_id,
            user_id=user_id,
            token_hash=keyed_token_hash(self._key, token),
            created_at=now,
            expires_at=now + ttl,
            user_agent=user_agent,
        )
        return IssuedSessionData(
            session_id=session_id, token=token, created_at=now, expires_at=now + ttl
        )

    def authenticate(self, token: str, *, now: datetime) -> tuple[uuid.UUID, uuid.UUID] | None:
        """Resolve a token to (session_id, user_id), or None (unknown/revoked/expired)."""
        digest = keyed_token_hash(self._key, token)
        for row in self._rows.values():
            if hmac.compare_digest(row.token_hash, digest):
                if row.revoked_at is not None or row.expires_at <= now:
                    return None
                return (row.session_id, row.user_id)
        return None

    def revoke(self, session_id: uuid.UUID) -> None:
        """Revoke one session (idempotent)."""
        row = self._rows.get(session_id)
        if row is not None and row.revoked_at is None:
            self._rows[session_id] = _SessionRow(
                session_id=row.session_id,
                user_id=row.user_id,
                token_hash=row.token_hash,
                created_at=row.created_at,
                expires_at=row.expires_at,
                revoked_at=self._clock.now(),
                user_agent=row.user_agent,
            )

    def revoke_all_for_user(self, user_id: uuid.UUID) -> int:
        """Revoke every live session of the user; return how many were revoked."""
        revoked = 0
        for session_id, row in self._rows.items():
            if row.user_id == user_id and row.revoked_at is None:
                self.revoke(session_id)
                revoked += 1
        return revoked

    def rotate(self, old_session_id: uuid.UUID, *, ttl: timedelta) -> IssuedSessionData:
        """Replace a live session with a fresh token (rotation on privilege change)."""
        row = self._rows.get(old_session_id)
        if row is None or row.revoked_at is not None:
            raise ValueError(f"session {old_session_id} is not live")
        issued = self.issue(user_id=row.user_id, ttl=ttl, user_agent=row.user_agent)
        self.revoke(old_session_id)
        return issued
