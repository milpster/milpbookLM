"""
PostgreSQL notebook-custody store (metadata-only custody operations, AD-022).

The ch05 schema has a two-valued notebooks.custody_state column; the domain's
three-phase custody record is reconstructed from the column plus the append-only
audit trail (the custody events), so no schema change is needed for the prototype.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from milpbooklm_domain.custody import CustodyEvent, CustodyPhase, CustodyRecord
from milpbooklm_domain.ownership import (
    CustodyState,
    MembershipRole,
    NotebookMembership,
    NotebookOwnership,
)

from milpbooklm_adapters.db.tables.blobs import audit_events
from milpbooklm_adapters.db.tables.collaboration import notebook_memberships, notebooks

# Domain custody phase -> the ch05 column value (scheduled deletion is a locked variant).
_COLUMN_FOR_PHASE: dict[str, str] = {
    CustodyPhase.NONE.value: "none",
    CustodyPhase.LOCKED.value: "locked_admin_custody",
    CustodyPhase.SCHEDULED_DELETION.value: "locked_admin_custody",
}

_COLUMN_TO_STATE: dict[str, CustodyState] = {
    "none": CustodyState.NONE,
    "locked_admin_custody": CustodyState.LOCKED_ADMIN_CUSTODY,
}

_CUSTODY_ACTIONS: tuple[str, ...] = (
    "custody.locked",
    "custody.transferred",
    "custody.scheduled_deletion",
)

# Sentinel for reconstructed events whose actor is unknown (audit actor_user_id
# is NULL-on-delete; the event itself is the source of truth for the phase).
UNKNOWN_ACTOR = uuid.UUID(int=0)


class PgNotebookCustodyStore:
    """The notebooks + notebook_memberships + audit_events custody adapter."""

    def __init__(self, engine: sa.engine.Engine) -> None:
        """Wire the engine."""
        self._engine = engine

    def sole_owned_notebook_ids(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        """Notebooks whose only owner membership belongs to the user."""
        owners_per_notebook = (
            sa.select(
                notebook_memberships.c.notebook_id.label("notebook_id"),
                sa.func.count().label("owners"),
            )
            .where(notebook_memberships.c.role == MembershipRole.OWNER.value)
            .group_by(notebook_memberships.c.notebook_id)
            .subquery()
        )
        with self._engine.begin() as conn:
            rows = conn.execute(
                sa.select(notebook_memberships.c.notebook_id).where(
                    notebook_memberships.c.user_id == user_id,
                    notebook_memberships.c.role == MembershipRole.OWNER.value,
                    notebook_memberships.c.notebook_id.in_(
                        sa.select(owners_per_notebook.c.notebook_id).where(
                            owners_per_notebook.c.owners == 1
                        )
                    ),
                )
            ).scalars()
        return list(rows)

    def load_ownership(
        self, notebook_id: uuid.UUID
    ) -> tuple[NotebookOwnership, CustodyRecord] | None:
        """(NotebookOwnership, CustodyRecord) for the notebook, or None."""
        with self._engine.begin() as conn:
            notebook = conn.execute(
                sa.select(
                    notebooks.c.custody_state, notebooks.c.owner_user_id
                ).where(notebooks.c.id == notebook_id)
            ).first()
            if notebook is None:
                return None
            membership_rows = conn.execute(
                sa.select(
                    notebook_memberships.c.user_id, notebook_memberships.c.role
                ).where(notebook_memberships.c.notebook_id == notebook_id)
            ).all()
            custody = conn.execute(
                sa.select(
                    audit_events.c.action,
                    audit_events.c.actor_user_id,
                    audit_events.c.details,
                    audit_events.c.created_at,
                )
                .where(
                    audit_events.c.subject_kind == "notebook",
                    audit_events.c.subject_id == notebook_id,
                    audit_events.c.action.in_(_CUSTODY_ACTIONS),
                )
                .order_by(audit_events.c.created_at.desc(), audit_events.c.id.desc())
                .limit(1)
            ).first()

        memberships = tuple(
            NotebookMembership(user_id=row.user_id, role=MembershipRole(row.role))
            for row in membership_rows
        )
        ownership = NotebookOwnership(
            memberships=memberships,
            custody_state=_COLUMN_TO_STATE[notebook.custody_state],
            denormalized_owner_pointer=notebook.owner_user_id,
        )
        return (
            ownership,
            self._custody_record(notebook_id, notebook.custody_state, custody),
        )

    def _custody_record(
        self,
        notebook_id: uuid.UUID,
        column_value: str,
        latest: sa.engine.Row[Any] | None,
    ) -> CustodyRecord:
        """Reconstruct the custody record from the column + the latest audit event."""
        if column_value == "none" or latest is None:
            return CustodyRecord(notebook_id=notebook_id, phase=CustodyPhase.NONE)
        details = latest.details or {}
        phase = (
            CustodyPhase.SCHEDULED_DELETION
            if latest.action == "custody.scheduled_deletion"
            else CustodyPhase.LOCKED
        )
        locked_reason = (
            details.get("scheduled_for")
            if phase is CustodyPhase.SCHEDULED_DELETION
            else details.get("reason", "admin_custody")
        )
        event = CustodyEvent(
            notebook_id=notebook_id,
            kind=latest.action,
            actor_id=latest.actor_user_id or UNKNOWN_ACTOR,
            at=latest.created_at,
            detail=details,
        )
        return CustodyRecord(
            notebook_id=notebook_id,
            phase=phase,
            locked_reason=locked_reason,
            events=(event,),
        )

    def save_custody(
        self, notebook_id: uuid.UUID, phase: str, *, scheduled_for: datetime | None
    ) -> None:
        """Persist the custody phase of a notebook (metadata-only write)."""
        with self._engine.begin() as conn:
            result = conn.execute(
                sa.update(notebooks)
                .where(notebooks.c.id == notebook_id)
                .values(custody_state=_COLUMN_FOR_PHASE[phase], revision=notebooks.c.revision + 1)
            )
            if result.rowcount == 0:
                raise ValueError(f"unknown notebook {notebook_id}")

    def add_owner_membership(
        self, notebook_id: uuid.UUID, user_id: uuid.UUID, granted_by: uuid.UUID
    ) -> None:
        """Record an ownership transfer (metadata-only custody operation)."""
        with self._engine.begin() as conn:
            existing = conn.execute(
                sa.select(notebook_memberships.c.id).where(
                    notebook_memberships.c.notebook_id == notebook_id,
                    notebook_memberships.c.user_id == user_id,
                )
            ).first()
            if existing is not None:
                conn.execute(
                    sa.update(notebook_memberships)
                    .where(notebook_memberships.c.id == existing.id)
                    .values(
                        role=MembershipRole.OWNER.value,
                        granted_by_user_id=granted_by,
                    )
                )
            else:
                conn.execute(
                    sa.insert(notebook_memberships).values(
                        notebook_id=notebook_id,
                        user_id=user_id,
                        role=MembershipRole.OWNER.value,
                        granted_by_user_id=granted_by,
                    )
                )
            # Keep the display-only owner pointer consistent with the membership truth.
            conn.execute(
                sa.update(notebooks)
                .where(notebooks.c.id == notebook_id)
                .values(owner_user_id=user_id)
            )

    def remove_member(self, notebook_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Remove a membership row (metadata-only custody operation)."""
        with self._engine.begin() as conn:
            conn.execute(
                sa.delete(notebook_memberships).where(
                    notebook_memberships.c.notebook_id == notebook_id,
                    notebook_memberships.c.user_id == user_id,
                )
            )
            conn.execute(
                sa.update(notebooks)
                .where(
                    notebooks.c.id == notebook_id,
                    notebooks.c.owner_user_id == user_id,
                )
                .values(owner_user_id=None)
            )
