"""Compute the public capability surface from the reviewed registry and runtime gates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import assert_never

from milpbooklm_domain.capabilities import (
    CapabilityClassification,
    CapabilityDefinition,
    CapabilityReason,
    CapabilityState,
    DependencyId,
    EffectiveCapability,
    FeatureFlag,
)

PROVIDER_DEPENDENCY_SUFFIX = "_provider"


@dataclass(frozen=True, slots=True)
class CapabilityRuntime:
    """Installation policy and provider inputs applied to compiled support."""

    enabled_feature_flags: frozenset[FeatureFlag] = frozenset()
    configured_providers: frozenset[DependencyId] = frozenset()


def compute_capabilities(
    definitions: Sequence[CapabilityDefinition],
    runtime: CapabilityRuntime,
    dependency_health: Mapping[DependencyId, bool],
) -> tuple[EffectiveCapability, ...]:
    """Return every target capability with its effective installation state."""
    effective = (
        _compute_capability(definition, runtime, dependency_health) for definition in definitions
    )
    return tuple(capability for capability in effective if capability is not None)


def _compute_capability(
    definition: CapabilityDefinition,
    runtime: CapabilityRuntime,
    dependency_health: Mapping[DependencyId, bool],
) -> EffectiveCapability | None:
    state: CapabilityState
    reason: CapabilityReason | None
    match definition.classification:
        case CapabilityClassification.NON_TARGET:
            return None
        case CapabilityClassification.PROVISIONAL:
            state = CapabilityState.PROVISIONAL
            reason = CapabilityReason.PROVISIONAL_NOT_CLAIMED
        case (
            CapabilityClassification.STABLE
            | CapabilityClassification.ADVANCED
            | CapabilityClassification.OPTIONAL
        ):
            state, reason = _supported_state(definition, runtime, dependency_health)
        case unreachable:
            assert_never(unreachable)
    return _result(definition, state, reason)


def _supported_state(
    definition: CapabilityDefinition,
    runtime: CapabilityRuntime,
    dependency_health: Mapping[DependencyId, bool],
) -> tuple[CapabilityState, CapabilityReason | None]:
    if not definition.implemented:
        return (
            CapabilityState.DISABLED,
            CapabilityReason.COMPILED_SUPPORT_MISSING,
        )
    if not definition.enabled or (
        definition.feature_flag is not None
        and definition.feature_flag not in runtime.enabled_feature_flags
    ):
        return (
            CapabilityState.DISABLED,
            CapabilityReason.ADMIN_POLICY_DISABLED,
        )

    provider_dependencies = tuple(
        dependency
        for dependency in definition.dependencies
        if dependency.endswith(PROVIDER_DEPENDENCY_SUFFIX)
    )
    if any(provider not in runtime.configured_providers for provider in provider_dependencies):
        return (
            CapabilityState.DEGRADED,
            CapabilityReason.PROVIDER_NOT_CONFIGURED,
        )

    infrastructure_dependencies = tuple(
        dependency
        for dependency in definition.dependencies
        if not dependency.endswith(PROVIDER_DEPENDENCY_SUFFIX)
    )
    if any(
        not dependency_health.get(dependency, False) for dependency in infrastructure_dependencies
    ):
        return (
            CapabilityState.DEGRADED,
            CapabilityReason.DEPENDENCY_UNHEALTHY,
        )
    return CapabilityState.AVAILABLE, None


def _result(
    definition: CapabilityDefinition,
    state: CapabilityState,
    reason: CapabilityReason | None,
) -> EffectiveCapability:
    return EffectiveCapability(
        id=definition.id,
        name=definition.name,
        description=definition.description,
        classification=definition.classification,
        state=state,
        reason=reason,
    )
