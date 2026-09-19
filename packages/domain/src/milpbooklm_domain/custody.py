"""
Administrative-custody state machine (AD-022, ch17 §9).

A notebook must never become ownerless. When its sole owner is disabled or deleted,
the notebook enters locked administrative custody. Administrators may resolve custody
with metadata-only operations (ownership transfer or scheduled deletion); those
operations must NOT grant content access and must NOT add the administrator as a
content member. Every transition is audited.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from milpbooklm_domain.identity import User
from milpbooklm_domain.ownership import (
    CustodyState,
    MembershipRole,
    NotebookMembership,
    NotebookOwnership,
)


class CustodyPhase(StrEnum):
    """Custody phases: normal, locked, and scheduled for deletion."""

    NONE = "none"
    LOCKED = "locked"
    SCHEDULED_DELETION = "scheduled_deletion"


@dataclass(frozen=True, slots=True)
class CustodyEvent:
    """One audited custody transition (metadata-only: never carries content)."""

    notebook_id: uuid.UUID
    kind: str
    actor_id: uuid.UUID
    at: datetime
    detail: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CustodyRecord:
    """The custody fact of one notebook: phase plus the audit trail that produced it."""

    notebook_id: uuid.UUID
    phase: CustodyPhase = CustodyPhase.NONE
    locked_reason: str | None = None
    scheduled_for: datetime | None = None
    events: tuple[CustodyEvent, ...] = ()


class CustodyError(ValueError):
    """An illegal custody transition (guards in this module raise it)."""


def lock_custody(
    record: CustodyRecord,
    *,
    actor_id: uuid.UUID,
    reason: str,
    at: datetime,
) -> CustodyRecord:
    """Enter locked administrative custody (triggered by sole-owner disablement)."""
    if record.phase is not CustodyPhase.NONE:
        raise CustodyError(f"cannot lock a notebook in custody phase {record.phase.value}")
    event = CustodyEvent(
        notebook_id=record.notebook_id, kind="custody.locked", actor_id=actor_id, at=at,
        detail={"reason": reason},
    )
    return CustodyRecord(
        notebook_id=record.notebook_id,
        phase=CustodyPhase.LOCKED,
        locked_reason=reason,
        events=(*record.events, event),
    )


def transfer_custody(
    record: CustodyRecord,
    ownership: NotebookOwnership,
    *,
    new_owner: User,
    actor_id: uuid.UUID,
    at: datetime,
) -> tuple[NotebookOwnership, CustodyRecord]:
    """
    Metadata-only ownership transfer of a locked notebook (AD-022).

    Guards: the notebook must be locked; the new owner must be an active account;
    the administrator is never added as a content member and gains no content access.
    """
    if record.phase is not CustodyPhase.LOCKED:
        raise CustodyError(f"transfer requires a locked notebook, phase is {record.phase.value}")
    if not new_owner.enabled:
        raise CustodyError("custody transfer requires an active (enabled) new owner")
    if new_owner.id == actor_id:
        raise CustodyError("the acting administrator cannot take notebook ownership")
    memberships = tuple(m for m in ownership.memberships if m.user_id is not new_owner.id)
    if new_owner.id not in frozenset(m.user_id for m in memberships):
        memberships = (
            *memberships,
            NotebookMembership(user_id=new_owner.id, role=MembershipRole.OWNER),
        )
    if actor_id in frozenset(m.user_id for m in memberships):
        # Defense in depth: the acting admin must never become a content member.
        raise CustodyError("custody transfer must not add the acting administrator as a member")
    event = CustodyEvent(
        notebook_id=record.notebook_id,
        kind="custody.transferred",
        actor_id=actor_id,
        at=at,
        detail={"new_owner": str(new_owner.id)},
    )
    new_ownership = NotebookOwnership(
        memberships=memberships,
        custody_state=CustodyState.NONE,
        denormalized_owner_pointer=new_owner.id,
    )
    return new_ownership, CustodyRecord(
        notebook_id=record.notebook_id,
        phase=CustodyPhase.NONE,
        events=(*record.events, event),
    )


def schedule_deletion(
    record: CustodyRecord,
    *,
    actor_id: uuid.UUID,
    scheduled_for: datetime,
    at: datetime,
) -> CustodyRecord:
    """Schedule deletion of a locked notebook (resolves custody without content access)."""
    if record.phase is not CustodyPhase.LOCKED:
        raise CustodyError(
            f"scheduling deletion requires a locked notebook, phase is {record.phase.value}"
        )
    event = CustodyEvent(
        notebook_id=record.notebook_id,
        kind="custody.scheduled_deletion",
        actor_id=actor_id,
        at=at,
        detail={"scheduled_for": scheduled_for.isoformat()},
    )
    return CustodyRecord(
        notebook_id=record.notebook_id,
        phase=CustodyPhase.SCHEDULED_DELETION,
        locked_reason=record.locked_reason,
        scheduled_for=scheduled_for,
        events=(*record.events, event),
    )


def resolved_for_deletion(record: CustodyRecord) -> bool:
    """Return True when the notebook no longer blocks final account deletion."""
    return record.phase in (CustodyPhase.NONE, CustodyPhase.SCHEDULED_DELETION)
