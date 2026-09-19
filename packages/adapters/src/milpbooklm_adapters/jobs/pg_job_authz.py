"""
Authorization revalidation for background jobs (ch15 / AD-021, FND-05).

Accepting a job does not freeze authorization forever: the worker revalidates the
initiating actor's CURRENT permission before dispatch and before final publication
through the T4 policy engine and the same notebook reader the request path uses.
Revocation (disablement, membership loss) therefore stops further work: the worker
cancels the job durably instead of publishing.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from milpbooklm_application.policy_engine import NotebookAccess, PolicyEngine
from milpbooklm_application.ports import NotebookReader, UserRepository
from milpbooklm_domain.jobs import JobRecord
from milpbooklm_domain.policy import PolicyAction

from milpbooklm_adapters.db.tables.collaboration import notebooks

# Capability -> policy action for the baseline job kinds (the hook point future
# capabilities extend; notebook-bound jobs re-check the actor's notebook role).
_CAPABILITY_ACTIONS: dict[str, PolicyAction] = {
    "note_mutate": PolicyAction.NOTE_MUTATE,
    "source_mutate": PolicyAction.SOURCE_MUTATE,
    "studio_generate": PolicyAction.STUDIO_GENERATE,
    "research_run": PolicyAction.RESEARCH_RUN,
}
_DEFAULT_ACTION = PolicyAction.NOTE_MUTATE


class PolicyAuthzRevalidator:
    """Revalidate a job's initiating actor against the live policy engine (T4)."""

    def __init__(
        self,
        engine: sa.engine.Engine,
        policy_engine: PolicyEngine,
        users: UserRepository,
        notebooks: NotebookReader,
    ) -> None:
        """Wire the live policy engine and the request-path readers."""
        self._engine = engine
        self._policy_engine = policy_engine
        self._users = users
        self._notebooks = notebooks

    def revalidate(self, job: JobRecord) -> bool:
        """Return True when the actor may still run this job's capability right now."""
        actor = job.actor_user_id
        if actor is None:
            return True  # system/maintenance job: explicit system actor (ch15)
        user = self._users.get(actor)
        if user is None or not user.enabled:
            return False
        if job.notebook_id is None:
            return True  # installation-owned work: no notebook content access involved
        view = self._notebooks.notebook_with_membership(actor, job.notebook_id)
        if view is None:
            return False
        action = _CAPABILITY_ACTIONS.get(job.capability or "", _DEFAULT_ACTION)
        access = NotebookAccess(notebook_id=job.notebook_id, role=view.membership)
        return self._policy_engine.decide_notebook(user, access, action).allowed

    def notebook_exists(self, notebook_id: uuid.UUID) -> bool:
        """Whether a notebook row exists (enqueues against unknown notebooks are rejected)."""
        with self._engine.begin() as conn:
            row = conn.execute(
                sa.select(notebooks.c.id).where(notebooks.c.id == notebook_id)
            ).first()
        return row is not None
