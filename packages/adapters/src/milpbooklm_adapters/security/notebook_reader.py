"""
PostgreSQL notebook reader for the API (the query-layer authz surface).

``visible_notebooks`` applies the membership query filter; ``notebook_with_membership``
returns the row plus the user's role (None = no membership) so the handler-level
policy check can produce a decision with a stable reason (admin-without-membership
must 403, not silently 404).
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from milpbooklm_application.ports import NotebookView
from milpbooklm_domain.ownership import MembershipRole

from milpbooklm_adapters.db.tables.collaboration import notebook_memberships, notebooks
from milpbooklm_adapters.security.authz_filters import notebook_visibility


class PgNotebookReader:
    """Membership-aware notebook reads over the ch05 schema."""

    def __init__(self, engine: sa.engine.Engine) -> None:
        """Wire the engine."""
        self._engine = engine

    def _view(self, row: sa.engine.Row[Any]) -> NotebookView:
        """Build the API view from a table row (membership role may be NULL)."""
        return NotebookView(
            notebook_id=row.id,
            title=row.title,
            custody_state=row.custody_state,
            membership=MembershipRole(row.role) if row.role is not None else None,
        )

    def visible_notebooks(self, user_id: uuid.UUID) -> list[NotebookView]:
        """Return the notebooks the user may see (query filter: membership only)."""
        with self._engine.begin() as conn:
            rows = conn.execute(
                sa.select(
                    notebooks.c.id,
                    notebooks.c.title,
                    notebooks.c.custody_state,
                    notebook_memberships.c.role,
                )
                .outerjoin(
                    notebook_memberships,
                    (notebook_memberships.c.notebook_id == notebooks.c.id)
                    & (notebook_memberships.c.user_id == user_id),
                )
                .where(notebook_visibility(user_id))
                .order_by(notebooks.c.created_at, notebooks.c.id)
            ).all()
        return [self._view(row) for row in rows]

    def notebook_with_membership(
        self, user_id: uuid.UUID, notebook_id: uuid.UUID
    ) -> NotebookView | None:
        """Return one notebook only when the user has a membership row."""
        with self._engine.begin() as conn:
            row = conn.execute(
                sa.select(
                    notebooks.c.id,
                    notebooks.c.title,
                    notebooks.c.custody_state,
                    notebook_memberships.c.role,
                )
                .join(
                    notebook_memberships,
                    (notebook_memberships.c.notebook_id == notebooks.c.id)
                    & (notebook_memberships.c.user_id == user_id),
                )
                .where(notebooks.c.id == notebook_id)
            ).first()
        if row is None:
            return None
        return self._view(row)
