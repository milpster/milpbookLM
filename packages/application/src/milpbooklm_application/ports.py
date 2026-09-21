"""
Identity ports (application-layer contracts; adapters implement them).

No framework types cross these ports: adapters translate persistence/credential
mechanisms into the pure domain and value objects defined here.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from milpbooklm_domain.custody import CustodyRecord
from milpbooklm_domain.identity import User, UserStatus
from milpbooklm_domain.ownership import MembershipRole, NotebookOwnership


class Clock(Protocol):
    """A UTC clock (injected so use cases are deterministic)."""

    def now(self) -> datetime:
        """Return the current UTC time."""
        ...


class PasswordHasher(Protocol):
    """Adaptive password hashing (Argon2id); parameters are recorded per hash."""

    def hash(self, password: str) -> str:
        """Hash a plaintext password with the current calibrated parameters."""
        ...

    def verify(self, stored_hash: str, password: str) -> bool:
        """Check a password against a stored hash (hash carries its own params)."""
        ...

    def needs_rehash(self, stored_hash: str) -> bool:
        """Return True when the hash was made with weaker parameters than calibration."""
        ...

    def dummy_verify(self, password: str) -> bool:
        """Burn one full hash of work against a dummy (enumeration-resistance)."""
        ...


@dataclass(frozen=True, slots=True)
class IssuedSessionData:
    """Value object crossing the port: session identity + token (token is ephemeral)."""

    session_id: uuid.UUID
    token: str
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class UserRecord:
    """
    Account plus its stored hash.

    The hash crosses the port ONLY through this record; the domain User never
    carries password material.
    """

    user: User
    password_hash: str


class SessionTokenStore(Protocol):
    """256-bit opaque session tokens; only a keyed hash is persisted (ch17 §7)."""

    def issue(
        self, *, user_id: uuid.UUID, ttl: timedelta, user_agent: str | None = None
    ) -> IssuedSessionData:
        """Issue a new session for the user and persist its keyed hash + metadata."""
        ...

    def authenticate(self, token: str, *, now: datetime) -> tuple[uuid.UUID, uuid.UUID] | None:
        """Resolve a token to (session_id, user_id), or None (unknown/revoked/expired)."""
        ...

    def revoke(self, session_id: uuid.UUID) -> None:
        """Revoke one session (idempotent)."""
        ...

    def revoke_all_for_user(self, user_id: uuid.UUID) -> int:
        """Revoke every live session of the user; return how many were revoked."""
        ...

    def rotate(self, old_session_id: uuid.UUID, *, ttl: timedelta) -> IssuedSessionData:
        """Replace a live session with a fresh token (rotation on privilege change)."""
        ...


class UserRepository(Protocol):
    """Local account persistence (the users table)."""

    def create(
        self,
        *,
        email: str,
        display_name: str,
        password_hash: str,
        installation_admin: bool = False,
    ) -> User:
        """Create an account; raises ValueError on a duplicate email."""
        ...

    def get(self, user_id: uuid.UUID) -> User | None:
        """Return the account, or None."""
        ...

    def get_by_email(self, email: str) -> User | None:
        """Return the account for the exact email, or None."""
        ...

    def get_record(self, email: str) -> UserRecord | None:
        """Return the account with its stored hash (login path only), or None."""
        ...

    def set_status(self, user_id: uuid.UUID, status: UserStatus) -> User:
        """Move the account to a new lifecycle status; return the updated account."""
        ...

    def count(self) -> int:
        """Count accounts (bootstrap one-time guard)."""
        ...

    def any_installation_admin(self) -> bool:
        """Whether an installation administrator exists (bootstrap one-time guard)."""
        ...


@dataclass(frozen=True, slots=True)
class AuditRetentionReport:
    """
    Bounded-retention report for the append-only audit trail.

    The trail is immutable (DB trigger: no UPDATE/DELETE for the app role), so
    retention is a CONSERVATIVE report of which events are eligible for
    out-of-band purging (created before ``cutoff``) - it never mutates retained
    events. Physical purging of eligible events is a privileged, out-of-band
    operation that consumes this report.
    """

    eligible_count: int
    cutoff: datetime
    oldest_created: datetime | None
    newest_created: datetime | None


class AuditLog(Protocol):
    """Append-only audit trail (metadata only; content never enters audit rows)."""

    def record(
        self,
        *,
        actor_id: uuid.UUID | None,
        action: str,
        subject_kind: str | None = None,
        subject_id: uuid.UUID | None = None,
        details: dict[str, str] | None = None,
        request_id: str | None = None,
    ) -> None:
        """Append one audited event."""
        ...

    def retention_report(self, *, cutoff: datetime) -> AuditRetentionReport:
        """Report the events eligible for out-of-band purging (created before cutoff)."""
        ...


class NotebookCustodyStore(Protocol):
    """Persistence for notebook custody state (metadata only)."""

    def sole_owned_notebook_ids(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        """Notebooks whose only owner membership belongs to the user."""
        ...

    def load_ownership(
        self, notebook_id: uuid.UUID
    ) -> tuple[NotebookOwnership, CustodyRecord] | None:
        """(NotebookOwnership, CustodyRecord) for the notebook, or None."""
        ...

    def save_custody(
        self, notebook_id: uuid.UUID, phase: str, *, scheduled_for: datetime | None
    ) -> None:
        """Persist the custody phase of a notebook (metadata-only write)."""
        ...

    def add_owner_membership(
        self, notebook_id: uuid.UUID, user_id: uuid.UUID, granted_by: uuid.UUID
    ) -> None:
        """Record an ownership transfer (metadata-only custody operation)."""
        ...

    def remove_member(self, notebook_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Remove a membership row (metadata-only custody operation)."""
        ...


class IdentityProvider(Protocol):
    """
    External identity assertion (OIDC / trusted proxy).

    Port + fakes only for this prototype (decision D8): no real adapter is built.
    """

    def assert_identity(self, *, peer: str, headers: Mapping[str, str]) -> uuid.UUID | None:
        """Resolve an identity assertion from a trusted peer to a user id, or None."""
        ...


@dataclass(frozen=True, slots=True)
class NotebookView:
    """One visible notebook row (metadata only) as read by the API layer."""

    notebook_id: uuid.UUID
    title: str
    custody_state: str
    membership: MembershipRole | None


class NotebookReader(Protocol):
    """Membership-aware notebook reads for the API (the query-layer authz surface)."""

    def visible_notebooks(self, user_id: uuid.UUID) -> list[NotebookView]:
        """Return the notebooks the user may see (query filter: membership only)."""
        ...

    def notebook_with_membership(
        self, user_id: uuid.UUID, notebook_id: uuid.UUID
    ) -> NotebookView | None:
        """One notebook + the user's role (None = no membership); the engine decides."""
        ...


class NotebookStore(Protocol):
    """Membership-scoped notebook creation (the ch05 owner-membership invariant)."""

    def create(self, *, title: str, actor_id: uuid.UUID) -> NotebookView:
        """Create a private notebook with the actor as sole owner; return its view."""
        ...
