"""Provider capability registry, policy filtering and local-first routing."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol

from milpbooklm_application.credentials import CredentialRef
from milpbooklm_application.models.contracts import ContentClassification, Modality, ModelRole
from milpbooklm_application.models.errors import ProviderErrorCode, ProviderFailureError


class ProviderTrust(StrEnum):
    """Configured provider locality/trust, never inferred from a hostname."""

    LOCAL = "local"
    TRUSTED_NETWORK = "trusted_network"
    EXTERNAL = "external"


class ProviderHealth(StrEnum):
    """Routing-visible provider health."""

    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class CapabilityDescriptor:
    """Probed capabilities whose use requires explicit administrator approval."""

    roles: frozenset[ModelRole]
    modalities: frozenset[Modality]
    features: frozenset[str]
    maximum_context: int
    structured_output: bool
    synchronous: bool = True
    mime_types: frozenset[str] = frozenset()
    languages: frozenset[str] = frozenset()
    supports_cancellation: bool = False
    provider_retains_content: bool | None = None
    probed: bool = False
    admin_approved: bool = False

    def approve(self) -> CapabilityDescriptor:
        """Return the immutable administrator-approved descriptor."""
        if not self.probed:
            raise ProviderFailureError(
                ProviderErrorCode.CAPABILITY_MISMATCH, "capabilities not probed"
            )
        return replace(self, admin_approved=True)


@dataclass(frozen=True, slots=True)
class ProviderCandidate:
    """Installation provider metadata kept separate from credential material."""

    config_id: uuid.UUID
    provider_kind: str
    display_name: str
    base_url: str
    trust: ProviderTrust
    descriptor: CapabilityDescriptor
    health: ProviderHealth = ProviderHealth.AVAILABLE
    cost_rank: int = 0
    credential: CredentialRef | None = None


@dataclass(frozen=True, slots=True)
class RoutingRequest:
    """All policy facts required before preference ordering is considered."""

    actor_user_id: uuid.UUID
    role: ModelRole
    modality: Modality
    required_capabilities: frozenset[str]
    content_classification: ContentClassification
    context_units: int
    structured_output: bool
    local_only: bool = False


class ProviderRegistry(Protocol):
    """Installation provider/config lookup port."""

    def candidates(self, actor_user_id: uuid.UUID) -> tuple[ProviderCandidate, ...]:
        """Return providers visible to the actor without decrypting credentials."""
        ...


def route_providers(
    candidates: tuple[ProviderCandidate, ...], request: RoutingRequest
) -> tuple[ProviderCandidate, ...]:
    """Filter policy/capability/ownership first, then rank local, health and cost."""
    allowed = tuple(candidate for candidate in candidates if _allows(candidate, request))
    return tuple(sorted(allowed, key=_rank))


def _allows(candidate: ProviderCandidate, request: RoutingRequest) -> bool:
    descriptor = candidate.descriptor
    credential_owner = (
        candidate.credential.owner_user_id if candidate.credential is not None else None
    )
    return (
        descriptor.probed
        and descriptor.admin_approved
        and candidate.health is not ProviderHealth.UNAVAILABLE
        and request.role in descriptor.roles
        and request.modality in descriptor.modalities
        and request.required_capabilities <= descriptor.features
        and request.context_units <= descriptor.maximum_context
        and (not request.structured_output or descriptor.structured_output)
        and (not request.local_only or candidate.trust is ProviderTrust.LOCAL)
        and (credential_owner is None or credential_owner == request.actor_user_id)
    )


def _rank(candidate: ProviderCandidate) -> tuple[int, int, int, str]:
    locality = 0 if candidate.trust is ProviderTrust.LOCAL else 1
    health = 0 if candidate.health is ProviderHealth.AVAILABLE else 1
    return locality, health, candidate.cost_rank, candidate.display_name
