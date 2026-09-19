"""Domain identity + policy matrix tests (fixture-truth decisions)."""

from __future__ import annotations

import uuid

from milpbooklm_application.policy_engine import PolicyEngine
from milpbooklm_application.policy_fixtures import BASELINE_MATRIX
from milpbooklm_domain.identity import User, UserStatus
from milpbooklm_domain.ownership import MembershipRole
from milpbooklm_domain.policy import (
    ADMIN_ACTIONS,
    CONTENT_ACTIONS,
    PolicyAction,
    PolicyActor,
    PolicyContext,
    PolicyReason,
    PolicyResource,
    ResourceKind,
    evaluate,
)

# ADMIN_ACTIONS cardinality in policy_fixtures (installation/users/providers/policy).
ADMIN_ACTION_COUNT = 4


def _actor(
    role: MembershipRole | None, *, admin: bool = False, enabled: bool = True
) -> PolicyActor:
    """Build a policy actor for one (role, admin, enabled) combination."""
    return PolicyActor(
        user_id=uuid.uuid4(),
        membership_role=role,
        installation_admin=admin,
        enabled=enabled,
    )


def _notebook() -> PolicyResource:
    """A synthetic notebook resource."""
    return PolicyResource(kind=ResourceKind.NOTEBOOK, notebook_id=uuid.uuid4())


def test_owner_reads_content_allowed() -> None:
    decision = evaluate(
        BASELINE_MATRIX, _actor(MembershipRole.OWNER), PolicyAction.READ_CONTENT, _notebook()
    )
    assert decision.allowed
    assert decision.reason is PolicyReason.ALLOW_MATRIX


def test_viewer_cannot_mutate_notes() -> None:
    decision = evaluate(
        BASELINE_MATRIX, _actor(MembershipRole.VIEWER), PolicyAction.NOTE_MUTATE, _notebook()
    )
    assert not decision.allowed
    assert decision.reason is PolicyReason.DENY_ROLE


def test_editor_cannot_change_provider_defaults() -> None:
    decision = evaluate(
        BASELINE_MATRIX, _actor(MembershipRole.EDITOR), PolicyAction.PROVIDER_DEFAULTS, _notebook()
    )
    assert not decision.allowed
    assert decision.reason is PolicyReason.DENY_ROLE


def test_admin_without_membership_denied_content() -> None:
    decision = evaluate(
        BASELINE_MATRIX, _actor(None, admin=True), PolicyAction.READ_CONTENT, _notebook()
    )
    assert not decision.allowed
    assert decision.reason is PolicyReason.DENY_NOT_MEMBER


def test_admin_powers_only_for_admins() -> None:
    allowed = evaluate(
        BASELINE_MATRIX,
        _actor(MembershipRole.OWNER, admin=True),
        PolicyAction.ADMIN_USERS,
        _notebook(),
    )
    denied = evaluate(
        BASELINE_MATRIX, _actor(MembershipRole.OWNER), PolicyAction.ADMIN_USERS, _notebook()
    )
    assert allowed.allowed
    assert allowed.reason is PolicyReason.ALLOW_ADMIN
    assert not denied.allowed
    assert denied.reason is PolicyReason.DENY_ROLE


def test_disabled_actor_denied_immediately() -> None:
    decision = evaluate(
        BASELINE_MATRIX,
        _actor(MembershipRole.OWNER, enabled=False),
        PolicyAction.READ_CONTENT,
        _notebook(),
    )
    assert not decision.allowed
    assert decision.reason is PolicyReason.DENY_DISABLED


def test_copy_gated_by_owner_policy() -> None:
    resource = _notebook()
    owner = _actor(MembershipRole.OWNER)
    forbidden = evaluate(
        BASELINE_MATRIX,
        owner,
        PolicyAction.COPY_NOTEBOOK,
        resource,
        PolicyContext(copy_permitted=False),
    )
    allowed = evaluate(
        BASELINE_MATRIX,
        owner,
        PolicyAction.COPY_NOTEBOOK,
        resource,
        PolicyContext(copy_permitted=True),
    )
    assert not forbidden.allowed
    assert forbidden.reason is PolicyReason.DENY_COPY_FORBIDDEN
    assert allowed.allowed
    assert allowed.reason is PolicyReason.ALLOW_CONTEXT


def test_source_restriction_reduces_owner_reading() -> None:
    decision = evaluate(
        BASELINE_MATRIX,
        _actor(MembershipRole.OWNER),
        PolicyAction.READ_CONTENT,
        _notebook(),
        PolicyContext(source_restriction_blocks=True),
    )
    assert not decision.allowed
    assert decision.reason is PolicyReason.DENY_SOURCE_RESTRICTION


def test_admin_actions_disjoint_from_content_actions() -> None:
    assert not (ADMIN_ACTIONS & CONTENT_ACTIONS)
    assert len(ADMIN_ACTIONS) == ADMIN_ACTION_COUNT


def test_engine_visible_for_requires_membership() -> None:
    engine = PolicyEngine()
    owner = User(id=uuid.uuid4(), email="owner@example.com", display_name="Owner")
    assert engine.visible_for(owner, MembershipRole.OWNER)
    assert engine.visible_for(owner, MembershipRole.VIEWER)
    assert not engine.visible_for(owner, None)


def test_user_status_transitions() -> None:
    user = User(id=uuid.uuid4(), email="u@example.com", display_name="U")
    assert user.status is UserStatus.ACTIVE
    assert user.enabled
    assert not user.disabled().enabled
    assert user.disabled().status is UserStatus.DISABLED
    assert user.deleted().status is UserStatus.DELETED
