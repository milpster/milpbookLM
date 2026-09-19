"""
Repository-level authorization query filters.

Repository queries include authorization filters and handlers also enforce
object-level decisions (ch17). These conditions mirror the PolicyEngine
visibility predicate: membership is the ONLY visibility grant, and
administration confers none (ARCH-17-002).
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa

from milpbooklm_adapters.db.tables.collaboration import notebook_memberships, notebooks
from milpbooklm_adapters.db.tables.sources import source_restrictions, sources


def notebook_visibility(user_id: uuid.UUID) -> sa.ColumnElement[bool]:
    """Build the notebook-membership filter (any role); admin grants no visibility."""
    return notebooks.c.id.in_(
        sa.select(notebook_memberships.c.notebook_id).where(
            notebook_memberships.c.user_id == user_id
        )
    )


def source_access_blocked(user_id: uuid.UUID) -> sa.ColumnElement[bool]:
    """Build the filter for sources whose active version is access_denied for the user."""
    blocked_versions = sa.select(source_restrictions.c.source_version_id).where(
        source_restrictions.c.restriction_type == "access_denied",
        sa.or_(
            source_restrictions.c.user_id == user_id,
            source_restrictions.c.user_id.is_(None),
        ),
    )
    return sources.c.current_version_id.in_(blocked_versions)
