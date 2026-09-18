"""VER-ARCH-01-003 (ARCH-01-003): external providers allowed unless policy disables.

Oracle: mixed configurations are permitted; the prohibited path (a
capability with external provider dependencies under a policy that disables
external providers) is specifically attempted and remains denied.
"""

from __future__ import annotations

from types import ModuleType

from tests._evidence import REPO_ROOT
from tests.meta._evidence_fnd02 import write_evidence_fnd02
from tests.meta._tools import load_tool

SYNTHETIC_PROVIDER_CAP = {
    "id": "synthetic_external_provider_capability",
    "name": "Synthetic external provider capability",
    "implemented": True,
    "enabled": True,
    "feature_flag": "cap.synthetic_external_provider_capability",
    "dependencies": ("postgresql", "chat_provider"),
}


def _policy_and_health(*, allow_external: bool) -> tuple[ModuleType, object, dict[str, bool]]:
    effective = load_tool("effective_state")
    policy = effective.CapabilityPolicy(
        allow_external_providers=allow_external,
        enabled_feature_flags=frozenset({SYNTHETIC_PROVIDER_CAP["feature_flag"]}),
    )
    health = dict.fromkeys(SYNTHETIC_PROVIDER_CAP["dependencies"], True)
    return effective, policy, health


def test_external_provider_allowed_by_default_policy() -> None:
    effective, policy, health = _policy_and_health(allow_external=True)
    state = effective.compute_effective_state(
        SYNTHETIC_PROVIDER_CAP, policy=policy, dependency_health=health
    )
    assert state.enabled is True, (
        "external providers must be allowed when policy does not disable them"
    )


def test_policy_denial_specifically_attempted_and_denied() -> None:
    effective, policy, health = _policy_and_health(allow_external=False)
    state = effective.compute_effective_state(
        SYNTHETIC_PROVIDER_CAP, policy=policy, dependency_health=health
    )
    assert state.enabled is False, "policy denial of external providers was ignored"
    assert "external providers disabled by policy" in state.reason
    assert "chat_provider" in state.reason


def test_notebook_policy_scope_carries_the_denial() -> None:
    from milpbooklm_api.config import NotebookPolicy
    from milpbooklm_api.config_loader import load_notebook_policy

    policy = load_notebook_policy({"allow_external_providers": False})
    assert policy.allow_external_providers is False
    default = NotebookPolicy()
    assert default.allow_external_providers is True, (
        "default must allow external providers (mixed configs)"
    )


def test_evidence_record_written() -> None:
    effective, policy, health = _policy_and_health(allow_external=False)
    denied = effective.compute_effective_state(
        SYNTHETIC_PROVIDER_CAP, policy=policy, dependency_health=health
    )
    write_evidence_fnd02(
        "VER-ARCH-01-003",
        "ARCH-01-003",
        "tests/architecture/dependencies/ver-arch-01-003.py",
        {
            "default_policy_allows_external": True,
            "denial_attempt": {"enabled": denied.enabled, "reason": denied.reason},
            "scope": "notebook policy (allow_external_providers)",
        },
    )
    evidence = REPO_ROOT / "artifacts" / "verification" / "VER-ARCH-01-003.json"
    assert evidence.exists()
