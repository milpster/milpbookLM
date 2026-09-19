"""
Administrative-custody use cases (AD-022, ch17 §9).

All operations here are installation-administrator powers: they are enforced
centrally in the use cases (never in route conditionals) and are metadata-only -
none of them grants the acting administrator notebook-content access or adds the
administrator as a content member. Every operation is audited.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from milpbooklm_domain.custody import (
    CustodyPhase,
    lock_custody,
    resolved_for_deletion,
    schedule_deletion,
    transfer_custody,
)
from milpbooklm_domain.identity import User, UserStatus
from milpbooklm_domain.ownership import owner_ids

from .errors import AccountNotFoundError, CustodyNotFoundError, PermissionDeniedError
from .ports import (
    AuditLog,
    Clock,
    NotebookCustodyStore,
    SessionTokenStore,
    UserRepository,
)


def _require_admin(users: UserRepository, actor_id: uuid.UUID) -> User:
    """Enforce the central admin-power gate for every custody operation."""
    actor = users.get(actor_id)
    if actor is None:
        raise AccountNotFoundError(f"actor {actor_id} is unknown")
    if not actor.installation_admin:
        raise PermissionDeniedError("installation administrator required")
    return actor


@dataclass(frozen=True, slots=True)
class DisableAccountOutcome:
    """The immediate effects of disabling an account (AD-022)."""

    user_id: uuid.UUID
    revoked_sessions: int
    locked_notebook_ids: tuple[uuid.UUID, ...]


class DisableAccount:
    """Disable a local account: sessions die immediately, sole-owned notebooks lock."""

    def __init__(
        self,
        users: UserRepository,
        sessions: SessionTokenStore,
        custody: NotebookCustodyStore,
        audit: AuditLog,
        clock: Clock,
    ) -> None:
        """Wire the ports the use case needs."""
        self._users = users
        self._sessions = sessions
        self._custody = custody
        self._audit = audit
        self._clock = clock

    def __call__(
        self, *, actor_id: uuid.UUID, user_id: uuid.UUID, request_id: str | None = None
    ) -> DisableAccountOutcome:
        """
        Disable the account and return the effect summary.

        Raises PermissionDeniedError for non-administrators and AccountNotFoundError
        for unknown ids.
        """
        actor = _require_admin(self._users, actor_id)
        user = self._users.get(user_id)
        if user is None:
            raise AccountNotFoundError(f"account {user_id} is unknown")
        if user.status is not UserStatus.ACTIVE:
            raise PermissionDeniedError(f"account is already {user.status.value}")
        # 1) Immediate: the account can no longer act (AD-022: disablement is immediate).
        self._users.set_status(user_id, UserStatus.DISABLED)
        # 2) Immediate: every live session is revoked.
        revoked = self._sessions.revoke_all_for_user(user_id)
        # 3) Sole-owned notebooks enter locked administrative custody.
        locked: list[uuid.UUID] = []
        at = self._clock.now()
        for notebook_id in self._custody.sole_owned_notebook_ids(user_id):
            loaded = self._custody.load_ownership(notebook_id)
            if loaded is None:
                continue
            _, record = loaded
            if record.phase is not CustodyPhase.NONE:
                continue
            locked_record = lock_custody(
                record, actor_id=actor.id, reason="sole_owner_disabled", at=at
            )
            self._custody.save_custody(
                notebook_id, locked_record.phase.value, scheduled_for=None
            )
            # The audit trail is the source of truth for the custody phase on the PG
            # store (it reconstructs from this notebook-scoped event, not the column).
            self._audit.record(
                actor_id=actor.id,
                action="custody.locked",
                subject_kind="notebook",
                subject_id=notebook_id,
                details={"reason": "sole_owner_disabled"},
                request_id=request_id,
            )
            locked.append(notebook_id)
        self._audit.record(
            actor_id=actor.id,
            action="account.disabled",
            subject_kind="user",
            subject_id=user_id,
            details={
                "revoked_sessions": str(revoked),
                "locked_notebooks": ",".join(str(n) for n in locked),
            },
            request_id=request_id,
        )
        return DisableAccountOutcome(
            user_id=user_id, revoked_sessions=revoked, locked_notebook_ids=tuple(locked)
        )


@dataclass(frozen=True, slots=True)
class CustodyTransferOutcome:
    """The effect of a metadata-only custody transfer."""

    notebook_id: uuid.UUID
    new_owner_id: uuid.UUID
    removed_owner_ids: tuple[uuid.UUID, ...]


class CustodyTransfer:
    """Transfer a locked notebook to a new owner (metadata-only; AD-022)."""

    def __init__(
        self,
        users: UserRepository,
        custody: NotebookCustodyStore,
        audit: AuditLog,
        clock: Clock,
    ) -> None:
        """Wire the ports the use case needs."""
        self._users = users
        self._custody = custody
        self._audit = audit
        self._clock = clock

    def __call__(
        self,
        *,
        actor_id: uuid.UUID,
        notebook_id: uuid.UUID,
        new_owner_id: uuid.UUID,
        request_id: str | None = None,
    ) -> CustodyTransferOutcome:
        """Move a locked notebook to the new owner; the acting admin gains no membership."""
        actor = _require_admin(self._users, actor_id)
        loaded = self._custody.load_ownership(notebook_id)
        if loaded is None:
            raise CustodyNotFoundError(f"notebook {notebook_id} is unknown")
        ownership, record = loaded
        new_owner = self._users.get(new_owner_id)
        if new_owner is None:
            raise AccountNotFoundError(f"new owner {new_owner_id} is unknown")
        removed = tuple(oid for oid in owner_ids(ownership) if oid is not new_owner_id)
        _new_ownership, new_record = transfer_custody(
            record, ownership, new_owner=new_owner, actor_id=actor.id, at=self._clock.now()
        )
        # Persist metadata-only: drop stale owner rows, add the new owner, unlock custody.
        for old_owner_id in removed:
            self._custody.remove_member(notebook_id, old_owner_id)
        self._custody.add_owner_membership(notebook_id, new_owner_id, actor.id)
        self._custody.save_custody(notebook_id, new_record.phase.value, scheduled_for=None)
        self._audit.record(
            actor_id=actor.id,
            action="custody.transferred",
            subject_kind="notebook",
            subject_id=notebook_id,
            details={
                "new_owner": str(new_owner_id),
                "removed_owners": ",".join(str(o) for o in removed),
            },
            request_id=request_id,
        )
        return CustodyTransferOutcome(
            notebook_id=notebook_id, new_owner_id=new_owner_id, removed_owner_ids=removed
        )


class ScheduleCustodyDeletion:
    """Schedule deletion of a locked notebook (resolves custody without content access)."""

    def __init__(
        self,
        users: UserRepository,
        custody: NotebookCustodyStore,
        audit: AuditLog,
        clock: Clock,
        horizon: timedelta,
    ) -> None:
        """Wire the ports the use case needs."""
        self._users = users
        self._custody = custody
        self._audit = audit
        self._clock = clock
        self._horizon = horizon

    def __call__(
        self,
        *,
        actor_id: uuid.UUID,
        notebook_id: uuid.UUID,
        request_id: str | None = None,
    ) -> datetime:
        """Return the scheduled deletion time (now + horizon)."""
        actor = _require_admin(self._users, actor_id)
        loaded = self._custody.load_ownership(notebook_id)
        if loaded is None:
            raise CustodyNotFoundError(f"notebook {notebook_id} is unknown")
        _, record = loaded
        at = self._clock.now()
        new_record = schedule_deletion(
            record, actor_id=actor.id, scheduled_for=at + self._horizon, at=at
        )
        scheduled_for = new_record.scheduled_for
        if scheduled_for is None:
            msg = "scheduled deletion lost its horizon"
            raise RuntimeError(msg)
        self._custody.save_custody(
            notebook_id, new_record.phase.value, scheduled_for=scheduled_for
        )
        self._audit.record(
            actor_id=actor.id,
            action="custody.scheduled_deletion",
            subject_kind="notebook",
            subject_id=notebook_id,
            details={"scheduled_for": scheduled_for.isoformat()},
            request_id=request_id,
        )
        return scheduled_for


@dataclass(frozen=True, slots=True)
class DeletionBlockers:
    """The account-deletion gate: sole-owned notebooks must have resolved custody."""

    user_id: uuid.UUID
    blocking_notebook_ids: tuple[uuid.UUID, ...]
    deletable: bool


class CheckAccountDeletable:
    """Report which sole-owned notebooks still block final account deletion (AD-022)."""

    def __init__(self, custody: NotebookCustodyStore) -> None:
        """Wire the ports the use case needs."""
        self._custody = custody

    def __call__(self, user_id: uuid.UUID) -> DeletionBlockers:
        """Return the deletion gate outcome for the account."""
        blocking: list[uuid.UUID] = []
        for notebook_id in self._custody.sole_owned_notebook_ids(user_id):
            loaded = self._custody.load_ownership(notebook_id)
            if loaded is None:
                continue
            _, record = loaded
            if not resolved_for_deletion(record):
                blocking.append(notebook_id)
        return DeletionBlockers(
            user_id=user_id, blocking_notebook_ids=tuple(blocking), deletable=not blocking
        )
