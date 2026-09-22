"""Public effective-capability gating surface (TECH-02-002)."""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import APIRouter
from milpbooklm_application.capabilities import CapabilityRuntime, compute_capabilities
from milpbooklm_domain.capabilities import (
    CapabilityClassification,
    CapabilityDefinition,
    CapabilityReason,
    CapabilityState,
    DependencyId,
)
from pydantic import BaseModel, ConfigDict

from .health_routes import ComponentHealth, ComponentState, DeploymentHealth


class CapabilityResponse(BaseModel):
    """One effective capability exposed to clients."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    classification: CapabilityClassification
    state: CapabilityState
    reason: CapabilityReason | None


class CapabilitiesResponse(BaseModel):
    """Installation-effective capability profile."""

    model_config = ConfigDict(frozen=True)

    capabilities: tuple[CapabilityResponse, ...]


def build_capability_router(
    definitions: tuple[CapabilityDefinition, ...],
    runtime: CapabilityRuntime,
    health: DeploymentHealth | None,
) -> APIRouter:
    """Build the unauthenticated frontend gating endpoint."""
    router = APIRouter()

    @router.get("/api/v1/capabilities", response_model=CapabilitiesResponse)
    async def capabilities() -> CapabilitiesResponse:
        effective = compute_capabilities(definitions, runtime, _dependency_health(health))
        return CapabilitiesResponse(
            capabilities=tuple(
                CapabilityResponse(
                    id=capability.id,
                    name=capability.name,
                    classification=capability.classification,
                    state=capability.state,
                    reason=capability.reason,
                )
                for capability in effective
            )
        )

    return router


def _dependency_health(health: DeploymentHealth | None) -> Mapping[DependencyId, bool]:
    if health is None:
        return {}
    components = {component.component: component for component in health.probe()}
    return {
        DependencyId("postgresql"): _ready(components, "database") and _ready(components, "schema"),
        DependencyId("blob_store"): _ready(components, "blob"),
        DependencyId("bubblewrap"): _ready(components, "execution_prerequisites"),
        # The parser registry is compiled into the deployment (isolated
        # subprocess parsers): it has no runtime component to probe, so the
        # dependency is satisfied whenever the deployment itself is healthy.
        DependencyId("parser_registry"): True,
    }


def _ready(components: Mapping[str, ComponentHealth], component: str) -> bool:
    result = components.get(component)
    return result is not None and result.state is ComponentState.READY
