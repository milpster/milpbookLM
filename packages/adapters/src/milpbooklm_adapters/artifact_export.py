"""
PostgreSQL export authorizer: revalidates membership + source restrictions.

The export path re-evaluates AD-023 effective access at BOTH request and
download time. This adapter resolves the actor's notebook membership through
the shared query layer, asks the policy engine for the object-level decision,
and checks the ``source_restrictions`` rows for the frozen manifest's source
versions (access_denied, global or per-user).
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from milpbooklm_application.artifact_export import ExportAuthorizer
from milpbooklm_application.policy_engine import NotebookAccess, PolicyEngine
from milpbooklm_application.ports import NotebookReader, UserRepository
from milpbooklm_domain.policy import PolicyAction, PolicyDecision, PolicyReason

from milpbooklm_adapters.db.tables.sources import source_restrictions


class PgExportAuthorizer(ExportAuthorizer):
    """DB-backed export revalidation (membership + per-source access restrictions)."""

    def __init__(
        self,
        engine: sa.engine.Engine,
        users: UserRepository,
        notebooks: NotebookReader,
        policy: PolicyEngine,
    ) -> None:
        """Wire the engine, account + membership query layers, and the policy engine."""
        self._engine = engine
        self._users = users
        self._notebooks = notebooks
        self._policy = policy

    def can_export(
        self,
        *,
        actor_id: uuid.UUID,
        notebook_id: uuid.UUID,
        source_version_ids: frozenset[uuid.UUID],
    ) -> PolicyDecision:
        """Decide export access: membership first, then source restrictions."""
        notebook = self._notebooks.notebook_with_membership(actor_id, notebook_id)
        if notebook is None:
            return PolicyDecision(False, PolicyReason.DENY_NOT_MEMBER)
        user = self._users.get(actor_id)
        if user is None:
            return PolicyDecision(False, PolicyReason.DENY_NOT_MEMBER)
        decision = self._policy.decide_notebook(
            user,
            NotebookAccess(notebook_id=notebook_id, role=notebook.membership),
            PolicyAction.READ_CONTENT,
        )
        if not decision.allowed:
            return decision
        if source_version_ids and self._any_restricted(actor_id, source_version_ids):
            return PolicyDecision(False, PolicyReason.DENY_SOURCE_RESTRICTION)
        return decision

    def _any_restricted(
        self, actor_id: uuid.UUID, source_version_ids: frozenset[uuid.UUID]
    ) -> bool:
        """Return True when any frozen source version carries access_denied."""
        with self._engine.begin() as connection:
            exists = connection.execute(
                sa.select(sa.literal(1))
                .where(
                    source_restrictions.c.source_version_id.in_(source_version_ids),
                    source_restrictions.c.restriction_type == "access_denied",
                    sa.or_(
                        source_restrictions.c.user_id.is_(None),
                        source_restrictions.c.user_id == actor_id,
                    ),
                )
                .limit(1)
            ).first()
        return exists is not None
