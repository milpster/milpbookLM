"""
PostgreSQL notebook creation store (ch05 owner-membership invariant).

Creation is one transaction: the notebook row and the actor's owner membership
are committed together, so a notebook can never exist without at least one
owner membership (the final-owner rule is satisfied by construction at birth).
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from milpbooklm_application.ports import NotebookView
from milpbooklm_domain.ownership import MembershipRole

from milpbooklm_adapters.db.tables.collaboration import notebook_memberships, notebooks


class PgNotebookStore:
    """Membership-scoped notebook creation over the ch05 schema."""

    def __init__(self, engine: sa.engine.Engine) -> None:
        """Wire the engine."""
        self._engine = engine

    def create(self, *, title: str, actor_id: uuid.UUID) -> NotebookView:
        """Create a private notebook owned by the actor; return its view."""
        with self._engine.begin() as conn:
            row = conn.execute(
                notebooks.insert()
                .values(
                    title=title,
                    owner_user_id=actor_id,
                    created_by_user_id=actor_id,
                )
                .returning(notebooks.c.id, notebooks.c.title, notebooks.c.custody_state)
            ).one()
            conn.execute(
                notebook_memberships.insert().values(
                    notebook_id=row.id,
                    user_id=actor_id,
                    role="owner",
                    granted_by_user_id=actor_id,
                )
            )
        return NotebookView(
            notebook_id=row.id,
            title=row.title,
            custody_state=row.custody_state,
            membership=MembershipRole.OWNER,
        )
