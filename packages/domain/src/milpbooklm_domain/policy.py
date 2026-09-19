"""
Centralized authorization policy: (actor, action, resource, context) -> allow/deny + reason.

The permission matrix is DATA (a :class:`PolicyMatrix` built from fixture rows), not
scattered route conditionals (ch17 §2.1). The engine evaluates, in order:

1. actor enabled (disablement is immediate - AD-022);
2. installation-admin powers (administrative actions only - administration never
   grants notebook-content access, ARCH-17-002);
3. notebook membership (admin-without-membership stays denied for content actions);
4. source/connector restrictions reduce any role's access (ARCH-17-015/016/017);
5. the matrix grant for (role, action), including conditional grants gated by context.

Baseline behavior must not become more permissive than the matrix without an explicit
policy/ADR (ARCH-17-003).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from milpbooklm_domain.ownership import MembershipRole


class PolicyAction(StrEnum):
    """Actions of the baseline permission matrix (ch17 §2.1) plus administrative powers."""

    # Notebook content
    READ_CONTENT = "read_content"
    CHAT_GROUNDED_PRIVATE = "chat_grounded_private"
    SOURCE_MUTATE = "source_mutate"
    NOTE_MUTATE = "note_mutate"
    STUDIO_GENERATE = "studio_generate"
    # Subject to installation/notebook provider/tool/execution policy (matrix footnote *).
    RESEARCH_RUN = "research_run"
    MEMBER_MANAGE = "member_manage"
    PROVIDER_DEFAULTS = "provider_defaults"
    COPY_PUBLICATION_POLICY = "copy_publication_policy"
    SHARE_LINK_MANAGE = "share_link_manage"
    COPY_NOTEBOOK = "copy_notebook"
    HARD_PURGE = "hard_purge"
    OWNERSHIP_TRANSFER = "ownership_transfer"
    NOTEBOOK_DELETE = "notebook_delete"
    # Installation administration (no implicit notebook-content role).
    ADMIN_INSTALLATION = "admin_installation"
    ADMIN_USERS = "admin_users"
    ADMIN_PROVIDERS = "admin_providers"
    ADMIN_POLICY = "admin_policy"


class PolicyReason(StrEnum):
    """Stable machine-readable decision reasons (surfaced verbatim in API 403 bodies)."""

    ALLOW_MATRIX = "allow:matrix"
    ALLOW_CONTEXT = "allow:context"
    ALLOW_ADMIN = "allow:admin"
    DENY_DISABLED = "deny:actor_disabled"
    DENY_NOT_MEMBER = "deny:not_member"
    DENY_ROLE = "deny:role"
    DENY_COPY_FORBIDDEN = "deny:copy_forbidden"
    DENY_SOURCE_RESTRICTION = "deny:source_restriction"


class Grant(StrEnum):
    """One matrix cell: an unconditional allow/deny, or a context-gated allow."""

    ALLOW = "allow"
    DENY = "deny"
    # Allowed only when PolicyContext.copy_permitted (owner-controlled copy policy).
    IF_COPY_PERMITTED = "if_copy_permitted"


@dataclass(frozen=True, slots=True)
class PolicyActor:
    """The principal a decision is about, as resolved by the application layer."""

    user_id: uuid.UUID
    membership_role: MembershipRole | None
    installation_admin: bool = False
    enabled: bool = True


class ResourceKind(StrEnum):
    """Kinds of resources an action applies to."""

    NOTEBOOK = "notebook"
    SOURCE = "source"
    ARTIFACT = "artifact"


@dataclass(frozen=True, slots=True)
class PolicyResource:
    """The object an action targets."""

    kind: ResourceKind
    notebook_id: uuid.UUID
    object_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class PolicyContext:
    """
    Request-level facts that gate conditional matrix cells.

    ``source_restriction_blocks`` is the generic connector/source-restriction hook
    (ARCH-17-017): it is True when the resource involves a restricted source the actor
    has no grant for, and reduces ANY role's access, owner included.
    """

    copy_permitted: bool = False
    source_restriction_blocks: bool = False


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """An authorization decision with its stable reason (never a bare bool)."""

    allowed: bool
    reason: PolicyReason


@dataclass(frozen=True, slots=True)
class PolicyMatrix:
    """The role x action permission matrix as data (fixture-loaded, never hard-coded logic)."""

    grants: dict[tuple[MembershipRole, PolicyAction], Grant] = field(compare=True)

    def grant(self, role: MembershipRole, action: PolicyAction) -> Grant:
        """Return the matrix cell for (role, action); absence of a cell is a denial."""
        return self.grants.get((role, action), Grant.DENY)


# Actions on which administration is the ONLY path (never granted by membership).
ADMIN_ACTIONS: frozenset[PolicyAction] = frozenset(
    {
        PolicyAction.ADMIN_INSTALLATION,
        PolicyAction.ADMIN_USERS,
        PolicyAction.ADMIN_PROVIDERS,
        PolicyAction.ADMIN_POLICY,
    }
)

# Content actions: installation administration confers none of these (ARCH-17-002).
CONTENT_ACTIONS: frozenset[PolicyAction] = frozenset(
    set(PolicyAction) - ADMIN_ACTIONS
)

# Matrix footnote *: these actions also depend on installation/notebook
# provider/tool/execution policy, re-evaluated by the caller's context.
POLICY_GATED_ACTIONS: frozenset[PolicyAction] = frozenset({PolicyAction.RESEARCH_RUN})

# Actions that read/expose source material and are therefore reduced by source
# restrictions (ARCH-17-015/016).
SOURCE_READING_ACTIONS: frozenset[PolicyAction] = frozenset(
    {
        PolicyAction.READ_CONTENT,
        PolicyAction.CHAT_GROUNDED_PRIVATE,
        PolicyAction.STUDIO_GENERATE,
        PolicyAction.RESEARCH_RUN,
    }
)


_EMPTY_CONTEXT = PolicyContext()


def evaluate(
    matrix: PolicyMatrix,
    actor: PolicyActor,
    action: PolicyAction,
    resource: PolicyResource,
    context: PolicyContext = _EMPTY_CONTEXT,
) -> PolicyDecision:
    """Decide (actor, action, resource, context) from the matrix; pure and deterministic."""
    if not actor.enabled:
        allowed, reason = False, PolicyReason.DENY_DISABLED
    elif action in ADMIN_ACTIONS:
        allowed, reason = actor.installation_admin, (
            PolicyReason.ALLOW_ADMIN if actor.installation_admin else PolicyReason.DENY_ROLE
        )
    elif actor.membership_role is None:
        # Content actions require notebook membership; administration is not a content role.
        allowed, reason = False, PolicyReason.DENY_NOT_MEMBER
    elif context.source_restriction_blocks and action in SOURCE_READING_ACTIONS:
        allowed, reason = False, PolicyReason.DENY_SOURCE_RESTRICTION
    else:
        grant = matrix.grant(actor.membership_role, action)
        if grant is Grant.ALLOW:
            allowed, reason = True, PolicyReason.ALLOW_MATRIX
        elif grant is Grant.IF_COPY_PERMITTED and context.copy_permitted:
            allowed, reason = True, PolicyReason.ALLOW_CONTEXT
        elif grant is Grant.IF_COPY_PERMITTED:
            allowed, reason = False, PolicyReason.DENY_COPY_FORBIDDEN
        else:
            allowed, reason = False, PolicyReason.DENY_ROLE
    return PolicyDecision(allowed, reason)
