"""
Deterministic in-memory fakes for the identity ports (unit tests + fakes-only paths).

Same behavioral contract as the PG adapters, no I/O. The OIDC/trusted-proxy
IdentityProvider fake is the D8 placeholder: no real adapter exists for this
prototype.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime

from milpbooklm_application.ports import NotebookView, UserRecord
from milpbooklm_domain.custody import CustodyPhase, CustodyRecord
from milpbooklm_domain.identity import User, UserStatus
from milpbooklm_domain.ownership import (
    CustodyState,
    MembershipRole,
    NotebookMembership,
    NotebookOwnership,
)


class InMemoryUserRepository:
    """The users port in memory (accounts + stored hashes + admin flag)."""

    def __init__(self) -> None:
        """Create an empty repository."""
        self._users: dict[uuid.UUID, User] = {}
        self._hashes: dict[uuid.UUID, str] = {}
        self._emails: dict[str, uuid.UUID] = {}

    def create(
        self,
        *,
        email: str,
        display_name: str,
        password_hash: str,
        installation_admin: bool = False,
    ) -> User:
        """Create an account; raises ValueError on a duplicate email."""
        if email in self._emails:
            raise ValueError(f"email {email!r} is already registered")
        user = User(
            id=uuid.uuid4(),
            email=email,
            display_name=display_name,
            status=UserStatus.ACTIVE,
            installation_admin=installation_admin,
            created_at=datetime.now(UTC),
        )
        self._users[user.id] = user
        self._hashes[user.id] = password_hash
        self._emails[email] = user.id
        return user

    def get(self, user_id: uuid.UUID) -> User | None:
        """Return the account, or None."""
        return self._users.get(user_id)

    def get_by_email(self, email: str) -> User | None:
        """Return the account for the exact email, or None."""
        user_id = self._emails.get(email)
        return self._users.get(user_id) if user_id is not None else None

    def get_record(self, email: str) -> UserRecord | None:
        """Return the account with its stored hash (login path only), or None."""
        user = self.get_by_email(email)
        if user is None:
            return None
        return UserRecord(user=user, password_hash=self._hashes[user.id])

    def set_status(self, user_id: uuid.UUID, status: UserStatus) -> User:
        """Move the account to a new lifecycle status; return the updated account."""
        user = self._users.get(user_id)
        if user is None:
            raise ValueError(f"unknown user {user_id}")
        updated = user.with_status(status)
        self._users[user_id] = updated
        return updated

    def count(self) -> int:
        """Count accounts (bootstrap one-time guard)."""
        return len(self._users)

    def any_installation_admin(self) -> bool:
        """Whether a live installation administrator exists (bootstrap one-time guard)."""
        return any(
            user.installation_admin and user.status is UserStatus.ACTIVE
            for user in self._users.values()
        )


AuditEntry = tuple[
    uuid.UUID | None, str, str | None, uuid.UUID | None, dict[str, str] | None, str | None
]


class InMemoryAuditLog:
    """The audit port in memory (inspection order)."""

    def __init__(self) -> None:
        """Create an empty audit trail."""
        self.entries: list[AuditEntry] = []

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
        self.entries.append((actor_id, action, subject_kind, subject_id, details, request_id))


class InMemoryNotebookCustodyStore:
    """The custody port in memory (notebook -> memberships/phases)."""

    def __init__(self) -> None:
        """Create an empty store."""
        self._memberships: dict[uuid.UUID, dict[uuid.UUID, MembershipRole]] = {}
        self._phases: dict[uuid.UUID, CustodyPhase] = {}
        self._scheduled: dict[uuid.UUID, datetime] = {}
        self._pointers: dict[uuid.UUID, uuid.UUID | None] = {}

    def add_notebook(self, notebook_id: uuid.UUID, owner_id: uuid.UUID) -> None:
        """Seed a notebook with its owner membership (test fixture helper)."""
        self._memberships.setdefault(notebook_id, {})[owner_id] = MembershipRole.OWNER
        self._phases.setdefault(notebook_id, CustodyPhase.NONE)
        self._pointers[notebook_id] = owner_id

    def sole_owned_notebook_ids(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        """Notebooks whose only owner membership belongs to the user."""
        result: list[uuid.UUID] = []
        for notebook_id, members in self._memberships.items():
            owners = [u for u, role in members.items() if role is MembershipRole.OWNER]
            if len(owners) == 1 and owners[0] == user_id:
                result.append(notebook_id)
        return result

    def load_ownership(
        self, notebook_id: uuid.UUID
    ) -> tuple[NotebookOwnership, CustodyRecord] | None:
        """(NotebookOwnership, CustodyRecord) for the notebook, or None."""
        if notebook_id not in self._memberships:
            return None
        memberships = tuple(
            NotebookMembership(user_id=user_id, role=role)
            for user_id, role in self._memberships[notebook_id].items()
        )
        phase = self._phases.get(notebook_id, CustodyPhase.NONE)
        state = (
            CustodyState.LOCKED_ADMIN_CUSTODY
            if phase is not CustodyPhase.NONE
            else CustodyState.NONE
        )
        ownership = NotebookOwnership(
            memberships=memberships,
            custody_state=state,
            denormalized_owner_pointer=self._pointers.get(notebook_id),
        )
        record = CustodyRecord(
            notebook_id=notebook_id,
            phase=phase,
            scheduled_for=self._scheduled.get(notebook_id),
        )
        return (ownership, record)

    def save_custody(
        self, notebook_id: uuid.UUID, phase: str, *, scheduled_for: datetime | None
    ) -> None:
        """Persist the custody phase of a notebook (metadata-only write)."""
        self._phases[notebook_id] = CustodyPhase(phase)
        if scheduled_for is not None:
            self._scheduled[notebook_id] = scheduled_for
        elif notebook_id in self._scheduled:
            del self._scheduled[notebook_id]

    def add_owner_membership(
        self, notebook_id: uuid.UUID, user_id: uuid.UUID, granted_by: uuid.UUID
    ) -> None:
        """Record an ownership transfer (metadata-only custody operation)."""
        self._memberships.setdefault(notebook_id, {})[user_id] = MembershipRole.OWNER
        self._pointers[notebook_id] = user_id

    def remove_member(self, notebook_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Remove a membership row (metadata-only custody operation)."""
        self._memberships.get(notebook_id, {}).pop(user_id, None)
        if self._pointers.get(notebook_id) == user_id:
            self._pointers[notebook_id] = None


class InMemoryNotebookReader:
    """The notebook reader port in memory (per-user views, no I/O)."""

    def __init__(self) -> None:
        """Create an empty reader."""
        self._notebooks: dict[uuid.UUID, tuple[str, str]] = {}
        self._memberships: dict[uuid.UUID, dict[uuid.UUID, MembershipRole]] = {}

    def add_view(self, user_id: uuid.UUID, view: NotebookView) -> None:
        """Record one notebook view for the user (test fixture helper)."""
        self._notebooks[view.notebook_id] = (view.title, view.custody_state)
        if view.membership is not None:
            self._memberships.setdefault(user_id, {})[view.notebook_id] = view.membership

    def visible_notebooks(self, user_id: uuid.UUID) -> list[NotebookView]:
        """Return the notebooks the query layer exposes to the user (membership only)."""
        views: list[NotebookView] = []
        for notebook_id, role in self._memberships.get(user_id, {}).items():
            title, custody_state = self._notebooks[notebook_id]
            views.append(
                NotebookView(
                    notebook_id=notebook_id,
                    title=title,
                    custody_state=custody_state,
                    membership=role,
                )
            )
        return views

    def notebook_with_membership(
        self, user_id: uuid.UUID, notebook_id: uuid.UUID
    ) -> NotebookView | None:
        """One notebook + the user's role (None = no membership); the engine decides."""
        if notebook_id not in self._notebooks:
            return None
        title, custody_state = self._notebooks[notebook_id]
        role = self._memberships.get(user_id, {}).get(notebook_id)
        return NotebookView(
            notebook_id=notebook_id,
            title=title,
            custody_state=custody_state,
            membership=role,
        )


class FakeIdentityProvider:
    """D8 fake: asserts an external identity without a real OIDC/trusted-proxy IdP."""

    def __init__(self) -> None:
        """Create an empty provider (no grants)."""
        self._grants: dict[tuple[str, str, str], uuid.UUID] = {}

    def grant(self, peer: str, header: str, value: str, user_id: uuid.UUID) -> None:
        """Allow ``peer`` to assert identity via header ``header: value`` as the user."""
        self._grants[(peer, header, value)] = user_id

    def assert_identity(self, *, peer: str, headers: Mapping[str, str]) -> uuid.UUID | None:
        """Resolve an identity assertion from a trusted peer to a user id, or None."""
        for (allowed_peer, header, value), user_id in self._grants.items():
            if allowed_peer == peer and headers.get(header) == value:
                return user_id
        return None
