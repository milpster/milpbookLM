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
    CapabilityClassification,
    CapabilityDefinition,
    CapabilityId,
    CapabilityReason,
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
        "source_pdf",
    }
)

HEALTHY_DEPENDENCIES = {
    DependencyId(dep): True for dep in ("postgresql", "blob_store", "parser_registry")
}
CORE_PROVIDERS = frozenset(
    {DependencyId("chat_provider"), DependencyId("embedding_provider")}
)

IMPLEMENTED_EVIDENCE = {
    "notebook_management": (
        "apps/api/notebook_routes.py: notebook routes + tests/unit/test_api_auth.py"
    ),
    "notebook_instructions": "apps/api/conversation_routes.py: chat configuration payload",
    "notebook_overview": "apps/api/notebook_overview_routes.py: overview route",
    "sources": "apps/api/source_routes.py: source collection/import/lifecycle routes",
    "source_guide": "apps/api/source_guide_routes.py: source guide route",
    "source_organization": "apps/api/source_lifecycle_routes.py: selection/metadata routes",
    "grounded_chat": "apps/api/conversation_routes.py + apps/api/retrieval_routes.py",
    "chat_configuration": "apps/api/conversation_routes.py: ConversationConfigRequest",
    "chat_lifecycle": "apps/api/conversation_routes.py: private conversation lifecycle",
    "citations": "apps/api/grounding_routes.py + tests/unit/db/test_note_routes.py",
    "notes": "apps/api/note_mutation_routes.py + tests/unit/db/test_note_routes.py",
    "artifact_lifecycle": "apps/api/artifact_routes.py + tests/unit/db/test_artifact_store.py",
    "source_markdown": "parsers/child.py:text/markdown -> parse_markdown + tests/fixtures/sources",
    "source_docx": "parsers/child.py:docx -> parse_docx + tests/fixtures/sources",
    "source_pptx": (
        "parsers/child.py:pptx -> parse_pptx + tests/fixtures/sources/ver-ingest-golden-001.py"
    ),
    "source_csv": "parsers/child.py:text/csv -> parse_csv + tests/fixtures/sources",
    "source_spreadsheet_files_formats": (
        "parsers/child.py:xlsx -> parse_xlsx + tests/fixtures/sources"
    ),
    "source_images": "parsers/child.py:image/* -> parse_image + tests/fixtures/sources",
    "source_audio": "parsers/child.py:audio/* -> parse_media + tests/fixtures/sources",
    "source_epub_files": (
        "parsers/child.py:application/epub+zip -> parse_epub + tests/fixtures/sources"
    ),
    "source_web_urls": "apps/api/source_import_routes.py:/web-url + application/web_fetch.py",
    "source_public_youtube_urls_transcript_backed_video_sources": (
        "apps/api/source_import_routes.py:/public-video + application/public_video.py"
    ),
    "source_pdf": (
        "source_import_routes.py:/import -> byte sniffing -> ingestion.parse -> "
        "canonical persistence -> SourceActivationStore + tests/unit/db/test_pdf_ingestion.py"
    ),
}

PROVISIONAL_EVIDENCE = {
    "evolving_note_integration": "announced/provisional; no implemented route or adapter",
    "editable_study_aids_and_performance_follow_up": (
        "announced/provisional; no implemented route or adapter"
    ),
    "realtime_notebook_voice_chat": "announced/provisional; no implemented route or adapter",
    "recorded_audio_capture": "announced/provisional; no implemented route or adapter",
}

DISABLED_EVIDENCE = {
    "agentic_chat": "no implemented agent/tool-capable route; future research dependency",
    "reports": "no implemented report route or recipe",
    "interactive_learning_overview": "no implemented interactive-learning route or recipe",
    "data_tables": "no implemented data-table route or recipe",
    "mind_maps": "no implemented mind-map route or recipe",
    "flashcards": "no implemented flashcard route or recipe",
    "quizzes": "no implemented quiz route or recipe",
    "audio_overview": "no implemented audio-overview route or provider adapter",
    "interactive_audio_overview": (
        "no implemented interactive-audio route or provider adapter"
    ),
    "video_overview": "no implemented video-overview route or media recipe",
    "cinematic_video": "no implemented cinematic-video route or media recipe",
    "slide_decks": "no implemented slide-deck route or renderer recipe",
    "infographics": "no implemented infographic route or renderer recipe",
    "starter_artifacts": "no implemented starter-artifact route or lifecycle hook",
    "source_discovery": (
        "no implemented discovery route; research route is not source discovery"
    ),
    "deep_research": "no implemented deep-research execution adapter",
    "code_data_analysis": (
        "no implemented analysis route; bubblewrap probe is not execution support"
    ),
    "private_sharing": "no implemented private-sharing route or ACL adapter",
    "public_notebooks": "no implemented public-notebook route or signed-link adapter",
    "notebook_copying": "no implemented notebook-copy route",
    "featured_published_notebooks": "no implemented publishing/discovery route",
    "usage_analytics": "no implemented product-analytics route",
    "restricted_connector_sources": "no implemented connector restriction adapter",
    "output_language": "no implemented user preference route",
    "appearance": "no implemented appearance preference route",
    "responsive_web_access": "architecture property, not a separately implemented capability route",
    "custom_providers": "no implemented provider-configuration route",

    "source_plain_text_and_pasted_text": (
        "paste route/parser exist, but source-family activation is not promoted "
        "from parser presence"
    ),
    "source_optional_authenticated_restricted_repositories_through_generic_connectors": (
        "no connector adapter"
    ),
    "source_optional_cloud_document_storage_connectors_implemented_through_generic_adapters": (
        "no connector adapter"
    ),
}

TARGET_AUDIT_EVIDENCE = {**IMPLEMENTED_EVIDENCE, **PROVISIONAL_EVIDENCE, **DISABLED_EVIDENCE}


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


def test_every_target_capability_has_audited_evidence_and_conservative_state() -> None:
    definitions = load_capability_registry()
    target_ids = {
        definition.id
        for definition in definitions
        if definition.classification is not CapabilityClassification.NON_TARGET
    }
    assert target_ids == set(TARGET_AUDIT_EVIDENCE)
    assert all(TARGET_AUDIT_EVIDENCE[capability_id].strip() for capability_id in target_ids)

    runtime = CapabilityRuntime(
        enabled_feature_flags=frozenset(
            definition.feature_flag
            for definition in definitions
            if definition.feature_flag is not None
        ),
        configured_providers=frozenset(
            dependency
            for definition in definitions
            for dependency in definition.dependencies
            if dependency.endswith("_provider")
        ),
    )
    dependency_health = {
        dependency: True
        for definition in definitions
        for dependency in definition.dependencies
    }
    effective = {
        capability.id: capability
        for capability in compute_capabilities(definitions, runtime, dependency_health)
    }

    for definition in definitions:
        if definition.classification is CapabilityClassification.NON_TARGET:
            assert definition.id not in effective
            continue
        capability = effective[definition.id]
        if definition.id in PROVISIONAL_EVIDENCE:
            assert capability.state is CapabilityState.PROVISIONAL
            assert capability.reason is CapabilityReason.PROVISIONAL_NOT_CLAIMED
        elif not definition.implemented:
            assert capability.state is CapabilityState.DISABLED
            assert capability.reason is CapabilityReason.COMPILED_SUPPORT_MISSING
        elif not definition.enabled:
            assert capability.state is CapabilityState.DISABLED
            assert capability.reason is CapabilityReason.ADMIN_POLICY_DISABLED
        else:
            assert capability.state is CapabilityState.AVAILABLE
            assert capability.reason is None

    registry = {definition.id: definition for definition in definitions}
    assert registry[CapabilityId("notes")].implemented is True
    assert registry[CapabilityId("notes")].enabled is False
    assert registry[CapabilityId("source_pdf")].implemented is True
    assert registry[CapabilityId("source_pdf")].enabled is True
    assert registry[CapabilityId("source_plain_text_and_pasted_text")].implemented is False
    assert registry[CapabilityId("source_plain_text_and_pasted_text")].enabled is False
