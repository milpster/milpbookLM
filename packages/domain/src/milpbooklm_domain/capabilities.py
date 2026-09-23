"""Capability registry value objects and effective-state vocabulary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import NewType

CapabilityId = NewType("CapabilityId", str)
FeatureFlag = NewType("FeatureFlag", str)
DependencyId = NewType("DependencyId", str)


class CapabilityClassification(StrEnum):
    """Architecture classifications carried by the reviewed registry."""

    STABLE = "stable/core"
    ADVANCED = "advanced/provider-dependent"
    OPTIONAL = "late/optional"
    PROVISIONAL = "provisional/announced"
    NON_TARGET = "deliberate-non-target"


class CapabilityState(StrEnum):
    """Effective states consumed by clients for feature gating."""

    AVAILABLE = "available"
    DISABLED = "disabled"
    DEGRADED = "degraded"
    PROVISIONAL = "provisional"


class CapabilityReason(StrEnum):
    """Bounded, secret-free reasons for an unavailable capability."""

    COMPILED_SUPPORT_MISSING = "compiled_support_missing"
    ADMIN_POLICY_DISABLED = "admin_policy_disabled"
    PROVIDER_NOT_CONFIGURED = "provider_not_configured"
    DEPENDENCY_UNHEALTHY = "dependency_unhealthy"
    PROVISIONAL_NOT_CLAIMED = "provisional_not_claimed"


@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    """One reviewed registry entry parsed at the application boundary."""

    id: CapabilityId
    name: str
    description: str
    classification: CapabilityClassification
    implemented: bool
    enabled: bool
    feature_flag: FeatureFlag | None
    dependencies: tuple[DependencyId, ...]


@dataclass(frozen=True, slots=True)
class EffectiveCapability:
    """One client-visible capability after all runtime gates are applied."""

    id: CapabilityId
    name: str
    description: str
    classification: CapabilityClassification
    state: CapabilityState
    reason: CapabilityReason | None
