"""
Policy engine facade: the single entry point for authorization decisions.

Routes, use cases and job handlers all ask the engine; none of them re-derive
permissions locally (ch17: "repository queries include authorization filters;
handlers also enforce object-level decisions" - both layers call this engine).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from milpbooklm_domain.identity import User
from milpbooklm_domain.ownership import MembershipRole
from milpbooklm_domain.policy import (
    PolicyAction,
    PolicyActor,
    PolicyContext,
    PolicyDecision,
    PolicyMatrix,
    PolicyResource,
    ResourceKind,
    evaluate,
)

from .policy_fixtures import BASELINE_MATRIX

_EMPTY_CONTEXT = PolicyContext()


@dataclass(frozen=True, slots=True)
class NotebookAccess:
    """The application-layer view of one user's membership in one notebook."""

    notebook_id: uuid.UUID
    role: MembershipRole | None
    copy_permitted: bool = False
    source_restriction_blocks: bool = False


class PolicyEngine:
    """Decide (actor, action, resource, context) from the fixture matrix."""

    def __init__(self, matrix: PolicyMatrix = BASELINE_MATRIX) -> None:
        """Bind the engine to a matrix (the fixture instance by default)."""
        self._matrix = matrix

    def decide(
        self,
        actor: PolicyActor,
        action: PolicyAction,
        resource: PolicyResource,
        context: PolicyContext = _EMPTY_CONTEXT,
    ) -> PolicyDecision:
        """Return the allow/deny decision plus its stable reason code."""
        return evaluate(self._matrix, actor, action, resource, context)

    def decide_notebook(
        self, user: User, notebook: NotebookAccess, action: PolicyAction
    ) -> PolicyDecision:
        """Object-level decision for a notebook action (the handler-level check)."""
        actor = PolicyActor(
            user_id=user.id,
            membership_role=notebook.role,
            installation_admin=user.installation_admin,
            enabled=user.enabled,
        )
        resource = PolicyResource(kind=ResourceKind.NOTEBOOK, notebook_id=notebook.notebook_id)
        context = PolicyContext(
            copy_permitted=notebook.copy_permitted,
            source_restriction_blocks=notebook.source_restriction_blocks,
        )
        return self.decide(actor, action, resource, context)

    def decide_as(
        self, user: User, membership: MembershipRole | None, action: PolicyAction
    ) -> PolicyDecision:
        """Return the decision for a synthetic membership (query filters, admin probes)."""
        access = NotebookAccess(notebook_id=uuid.UUID(int=0), role=membership)
        return self.decide_notebook(user, access, action)

    def visible_for(self, user: User, role: MembershipRole | None) -> bool:
        """
        Return the repository-query visibility predicate for a membership.

        May the user see rows where their membership in the notebook is ``role``
        (None = no membership)? Membership is the ONLY visibility grant;
        administration confers none (ARCH-17-002). The engine is the single
        source of the predicate; the SQL filters in the adapters mirror it.
        """
        return self.decide_as(user, role, PolicyAction.READ_CONTENT).allowed

    def actor_for(self, user: User, membership: MembershipRole | None) -> PolicyActor:
        """Build the domain actor view for a user in a given notebook context."""
        return PolicyActor(
            user_id=user.id,
            membership_role=membership,
            installation_admin=user.installation_admin,
            enabled=user.enabled,
        )
