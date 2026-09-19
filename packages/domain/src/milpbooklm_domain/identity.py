"""
Identity entities: users and browser sessions (pure, stdlib-only).

Local accounts are the auth baseline (AD-018). Password material never lives in the
domain: only the opaque stored hash crosses the boundary. Session tokens are 256-bit
CSPRNG opaque values; only a keyed hash is ever persisted (ch17 §7).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class UserStatus(StrEnum):
    """Account lifecycle states (users.status check constraint in the ch05 schema)."""

    ACTIVE = "active"
    DISABLED = "disabled"
    DELETED = "deleted"


@dataclass(frozen=True, slots=True)
class User:
    """A local account (immutable value object)."""

    id: uuid.UUID
    email: str
    display_name: str
    status: UserStatus = UserStatus.ACTIVE
    # Installation administration powers (ch17 §2). Administration never implies
    # notebook-content access; the policy engine keeps the two orthogonal.
    installation_admin: bool = False
    created_at: datetime | None = None

    @property
    def enabled(self) -> bool:
        """Only active accounts may authenticate or act (AD-022: disablement is immediate)."""
        return self.status is UserStatus.ACTIVE

    def with_status(self, status: UserStatus) -> User:
        """Return a copy in the new status; the original is unchanged."""
        return User(
            id=self.id,
            email=self.email,
            display_name=self.display_name,
            status=status,
            installation_admin=self.installation_admin,
            created_at=self.created_at,
        )

    def disabled(self) -> User:
        """Return a copy with the disabled status."""
        return self.with_status(UserStatus.DISABLED)

    def deleted(self) -> User:
        """Return a tombstoned copy (non-login identity; AD-022)."""
        return self.with_status(UserStatus.DELETED)


@dataclass(frozen=True, slots=True)
class Session:
    """Server-side session record: metadata + keyed token hash only, never the token."""

    session_id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    user_agent: str | None = None

    @property
    def active(self) -> bool:
        """A session is usable only while unrevoked; expiry is checked with a clock."""
        return self.revoked_at is None
