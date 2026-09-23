"""Effective-capability surface over the reviewed registry (TECH-02-002 gates).

Given:  the packaged reviewed registry and installation runtime inputs.
When:   the effective surface is computed.
Then:   exactly the implemented core surface reaches available when its
        dependencies are healthy; availability is never inferred for
        unimplemented capabilities no matter which flags or providers are set.
"""

from __future__ import annotations

from http import HTTPStatus

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from milpbooklm_api.capability_registry import RegistryEntry, load_capability_registry
from milpbooklm_api.capability_routes import build_capability_router
from milpbooklm_application.capabilities import CapabilityRuntime, compute_capabilities
from milpbooklm_domain.capabilities import (
    CapabilityDefinition,
    CapabilityId,
    CapabilityState,
    DependencyId,
    FeatureFlag,
)
from pydantic import ValidationError

EXPECTED_CAPABILITY_COUNT = 61
NOTEBOOK_MANAGEMENT_DESCRIPTION = (
    "Create, organize, duplicate, share, and manage notebook metadata."
)

IMPLEMENTED_CORE = frozenset(
    {
        "notebook_management",
        "notebook_overview",
        "notebook_instructions",
        "sources",
        "source_guide",
        "source_organization",
        "grounded_chat",
        "chat_configuration",
        "chat_lifecycle",
        "citations",
        "source_markdown",
        "source_csv",
        "source_spreadsheet_files_formats",
        "source_docx",
        "source_pptx",
        "source_epub_files",
        "source_web_urls",
        "source_images",
        "source_audio",
        "source_public_youtube_urls_transcript_backed_video_sources",
    }
)

HEALTHY_DEPENDENCIES = {
    DependencyId(dep): True for dep in ("postgresql", "blob_store", "parser_registry")
}
CORE_PROVIDERS = frozenset(
    {DependencyId("chat_provider"), DependencyId("embedding_provider")}
)


def _effective(
    definitions: tuple[CapabilityDefinition, ...], runtime: CapabilityRuntime
) -> dict[str, CapabilityState]:
    return {
        capability.id: capability.state
        for capability in compute_capabilities(definitions, runtime, HEALTHY_DEPENDENCIES)
    }


def test_registry_flip_matches_the_expected_core_surface() -> None:
    implemented = {
        definition.id
        for definition in load_capability_registry()
        if definition.implemented and definition.enabled
    }
    assert implemented == IMPLEMENTED_CORE


def test_registry_has_a_specific_description_for_every_capability() -> None:
    definitions = load_capability_registry()
    assert len(definitions) == EXPECTED_CAPABILITY_COUNT
    assert all(definition.description.strip() for definition in definitions)


def test_registry_entry_rejects_missing_or_blank_description() -> None:
    entry = {
        "id": "test_capability",
        "name": "Test capability",
        "classification": "stable/core",
        "implemented": False,
        "enabled": False,
        "feature_flag": None,
        "dependencies": [],
    }
    with pytest.raises(ValidationError):
        RegistryEntry.model_validate(entry)
    with pytest.raises(ValidationError):
        RegistryEntry.model_validate({**entry, "description": "  "})


def test_capability_description_reaches_the_http_response() -> None:
    app = FastAPI()
    app.include_router(
        build_capability_router(load_capability_registry(), CapabilityRuntime(), health=None)
    )
    response = TestClient(app).get("/api/v1/capabilities")
    assert response.status_code == HTTPStatus.OK
    capability = next(
        item for item in response.json()["capabilities"] if item["id"] == "notebook_management"
    )
    assert capability["description"] == NOTEBOOK_MANAGEMENT_DESCRIPTION


def test_implemented_core_surface_is_available_when_healthy() -> None:
    runtime = CapabilityRuntime(
        enabled_feature_flags=frozenset(
            FeatureFlag(f"cap.{capability_id}") for capability_id in IMPLEMENTED_CORE
        ),
        configured_providers=CORE_PROVIDERS,
    )
    effective = _effective(load_capability_registry(), runtime)
    for capability_id in IMPLEMENTED_CORE:
        assert effective[capability_id] is CapabilityState.AVAILABLE, capability_id


def test_core_surface_degrades_without_a_configured_embedding_provider() -> None:
    runtime = CapabilityRuntime(
        enabled_feature_flags=frozenset(
            FeatureFlag(f"cap.{capability_id}") for capability_id in IMPLEMENTED_CORE
        ),
        configured_providers=frozenset({DependencyId("chat_provider")}),
    )
    effective = _effective(load_capability_registry(), runtime)
    assert effective["grounded_chat"] is CapabilityState.DEGRADED
    assert effective["notebook_management"] is CapabilityState.AVAILABLE


def test_unimplemented_capabilities_stay_disabled_under_fully_satisfied_inputs() -> None:
    definitions = load_capability_registry()
    runtime = CapabilityRuntime(
        enabled_feature_flags=frozenset(
            FeatureFlag(definition.feature_flag)
            for definition in definitions
            if definition.feature_flag is not None
        ),
        configured_providers=frozenset(
            DependencyId(dependency)
            for dependency in (
                "chat_provider",
                "embedding_provider",
                "tts_provider",
                "stt_provider",
                "media_provider",
            )
        ),
    )
    every_dependency_healthy = {
        dependency: True for definition in definitions for dependency in definition.dependencies
    }
    effective = {
        capability.id: capability.state
        for capability in compute_capabilities(definitions, runtime, every_dependency_healthy)
    }
    for capability_id in (
        CapabilityId("agentic_chat"),
        CapabilityId("notes"),
        CapabilityId("audio_overview"),
        CapabilityId("code_data_analysis"),
    ):
        assert effective[capability_id] is CapabilityState.DISABLED, capability_id
