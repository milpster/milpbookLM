"""Effective-capability surface over the reviewed registry (TECH-02-002 gates).

Given:  the packaged reviewed registry and installation runtime inputs.
When:   the effective surface is computed.
Then:   exactly the implemented core surface reaches available when its
        dependencies are healthy; availability is never inferred for
        unimplemented capabilities no matter which flags or providers are set.
"""

from __future__ import annotations

from milpbooklm_api.capability_registry import load_capability_registry
from milpbooklm_application.capabilities import CapabilityRuntime, compute_capabilities
from milpbooklm_domain.capabilities import (
    CapabilityDefinition,
    CapabilityState,
    DependencyId,
    FeatureFlag,
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
    for capability_id in ("agentic_chat", "notes", "audio_overview", "code_data_analysis"):
        assert effective[capability_id] is CapabilityState.DISABLED, capability_id
