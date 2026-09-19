"""
Notebook ownership invariants (ch05 §3-4, ARCH-05-002).

The authoritative owner set is the set of owner MEMBERSHIPS. An optional denormalized
owner pointer (notebooks.owner_user_id) is display-only and MUST NOT be the authorization
source of truth. Every notebook has at least one owner OR an explicit locked
administrative-custody state.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum


class MembershipRole(StrEnum):
    """Membership roles (ch05 §3: owner, editor, viewer)."""

    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


class CustodyState(StrEnum):
    """Administrative custody of a notebook (ch05 mandatory invariants)."""

    NONE = "none"
    LOCKED_ADMIN_CUSTODY = "locked_admin_custody"


@dataclass(frozen=True, slots=True)
class NotebookMembership:
    """One user's role on one notebook."""

    user_id: uuid.UUID
    role: MembershipRole


@dataclass(frozen=True, slots=True)
class NotebookOwnership:
    """The ownership fact of a notebook: memberships + custody, optionally a stale pointer."""

    memberships: tuple[NotebookMembership, ...]
    custody_state: CustodyState = CustodyState.NONE
    denormalized_owner_pointer: uuid.UUID | None = None
    # Display-only pointer; never consulted by ownership_violation/can_remove_owner.
    _pointer_ignored: bool = field(default=True, compare=False, repr=False)


def owner_ids(ownership: NotebookOwnership) -> frozenset[uuid.UUID]:
    """Return the authoritative owner set (source of truth is memberships, ARCH-05-002)."""
    return frozenset(m.user_id for m in ownership.memberships if m.role is MembershipRole.OWNER)


def ownership_violation(ownership: NotebookOwnership) -> str | None:
    """Return a violation string, or None when the ownership invariant holds."""
    if not owner_ids(ownership) and ownership.custody_state is not (
        CustodyState.LOCKED_ADMIN_CUSTODY
    ):
        return "notebook has no owner membership and no locked administrative custody"
    return None


def can_remove_owner(ownership: NotebookOwnership, user_id: uuid.UUID) -> bool:
    """Final-owner rule: removable iff another owner remains or custody is locked."""
    if user_id not in owner_ids(ownership):
        return False
    if len(owner_ids(ownership)) > 1:
        return True
    return ownership.custody_state is CustodyState.LOCKED_ADMIN_CUSTODY


def authorize(ownership: NotebookOwnership, user_id: uuid.UUID, role: MembershipRole) -> bool:
    """Authorize a principal; the denormalized pointer must never grant access."""
    return user_id in owner_ids(ownership) and (role is MembershipRole.OWNER or True)
