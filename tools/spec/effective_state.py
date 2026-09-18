"""
Effective capability state computation (ch02 feature gating, ARCH-00-049).

The backend computes effective capability state from compiled support,
administrator policy, configured providers and dependency health; the
frontend consumes the emitted profile and never infers availability from
hidden buttons or provider names (TECH-02-002).

Skeleton semantics: a capability is effective only when every gate passes —
compiled support (implemented + enabled in the registry), an explicit feature
flag in policy, reported healthy dependencies, and external providers allowed
by policy whenever the capability depends on one. Any unmet gate keeps the
capability disabled with a machine-readable reason.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

# Dependencies whose name marks an external model/media provider. When
# policy denies external providers, these gate the capability.
PROVIDER_DEPENDENCY_MARKER = "_provider"


class CapabilityPolicy:
    """
    Administrator policy inputs gating effective capability state.

    ``allow_external_providers`` defaults to True (ARCH-01-002: external
    providers remain allowed unless explicitly disabled by policy).
    """

    __slots__ = ("allow_external_providers", "enabled_feature_flags")

    def __init__(
        self,
        allow_external_providers: bool = True,
        enabled_feature_flags: frozenset[str] = frozenset(),
    ) -> None:
        """Store the policy inputs verbatim."""
        self.allow_external_providers = allow_external_providers
        self.enabled_feature_flags = enabled_feature_flags


class EffectiveState:
    """Computed state for one capability: enabled flag + machine reason."""

    __slots__ = ("capability_id", "enabled", "reason")

    def __init__(self, capability_id: str, enabled: bool, reason: str) -> None:
        """Store the computed state for one capability."""
        self.capability_id = capability_id
        self.enabled = enabled
        self.reason = reason


def compute_effective_state(
    capability: Mapping[str, object],
    *,
    policy: CapabilityPolicy,
    dependency_health: Mapping[str, bool],
) -> EffectiveState:
    """Compute the effective state of one registry entry from all four gates."""
    cap_id = str(capability["id"])
    dependencies: Sequence[str] = cast_dependencies(capability)
    if not capability.get("implemented") or not capability.get("enabled"):
        return EffectiveState(
            cap_id, False, "no compiled support (not implemented/enabled in registry)"
        )
    feature_flag = capability.get("feature_flag")
    if feature_flag is not None and str(feature_flag) not in policy.enabled_feature_flags:
        return EffectiveState(cap_id, False, f"feature flag {feature_flag!r} not enabled by policy")
    unhealthy = [dep for dep in dependencies if not dependency_health.get(dep, False)]
    if unhealthy:
        return EffectiveState(
            cap_id, False, f"dependency health unmet: {', '.join(sorted(unhealthy))}"
        )
    provider_deps = [dep for dep in dependencies if PROVIDER_DEPENDENCY_MARKER in dep]
    if provider_deps and not policy.allow_external_providers:
        return EffectiveState(
            cap_id,
            False,
            f"external providers disabled by policy ({', '.join(sorted(provider_deps))})",
        )
    return EffectiveState(cap_id, True, "compiled support + policy + dependency health all met")


def compute_effective_states(
    capabilities: Sequence[Mapping[str, object]],
    *,
    policy: CapabilityPolicy,
    dependency_health: Mapping[str, bool],
) -> dict[str, EffectiveState]:
    """Compute effective states for a whole registry; keyed by capability id."""
    return {
        str(cap["id"]): compute_effective_state(
            cap, policy=policy, dependency_health=dependency_health
        )
        for cap in capabilities
    }


def cast_dependencies(capability: Mapping[str, object]) -> tuple[str, ...]:
    """Extract dependency names as a tuple (the registry schema guarantees strings)."""
    raw = capability.get("dependencies")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return ()
    return tuple(str(dep) for dep in raw)
