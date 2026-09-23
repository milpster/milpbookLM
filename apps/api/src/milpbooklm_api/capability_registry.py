"""Parse the packaged, reviewed capability registry into domain values."""

from __future__ import annotations

from importlib.resources import files

import yaml
from milpbooklm_domain.capabilities import (
    CapabilityClassification,
    CapabilityDefinition,
    CapabilityId,
    DependencyId,
    FeatureFlag,
)
from pydantic import BaseModel, ConfigDict, Field


class RegistryEntry(BaseModel):
    """Fields consumed at runtime from one reviewed registry entry."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str
    name: str
    description: str = Field(min_length=1, pattern=r".*\S.*")
    classification: CapabilityClassification
    implemented: bool
    enabled: bool
    feature_flag: str | None
    dependencies: tuple[str, ...]


class RegistryDocument(BaseModel):
    """Runtime projection of the reviewed registry document."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    capabilities: tuple[RegistryEntry, ...]


def load_capability_registry() -> tuple[CapabilityDefinition, ...]:
    """Load the sole packaged registry and convert it to domain definitions."""
    resource = files("milpbooklm_contracts").joinpath("capabilities.yaml")
    document = RegistryDocument.model_validate(yaml.safe_load(resource.read_text(encoding="utf-8")))
    return tuple(
        CapabilityDefinition(
            id=CapabilityId(entry.id),
            name=entry.name,
            description=entry.description,
            classification=entry.classification,
            implemented=entry.implemented,
            enabled=entry.enabled,
            feature_flag=(
                FeatureFlag(entry.feature_flag) if entry.feature_flag is not None else None
            ),
            dependencies=tuple(DependencyId(dependency) for dependency in entry.dependencies),
        )
        for entry in document.capabilities
    )
