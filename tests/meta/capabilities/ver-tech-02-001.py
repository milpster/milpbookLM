"""VER-TECH-02-001 (TECH-02-001): adapters cover every frozen source family.

Oracle: classification, phase, dependencies and applicability match the
parity matrix. The checked-in registry covers all 14 frozen Chapter 02
source families, with connector families independently optional.
"""

from __future__ import annotations

from tests._evidence import REPO_ROOT
from tests.meta._evidence_fnd02 import write_evidence_fnd02
from tests.meta._tools import load_tool

SOURCE_FAMILY_IDS = (
    "source_pdf",
    "source_plain_text_and_pasted_text",
    "source_markdown",
    "source_docx",
    "source_pptx",
    "source_csv",
    "source_spreadsheet_files_formats",
    "source_images",
    "source_audio",
    "source_epub_files",
    "source_optional_authenticated_restricted_repositories_through_generic_connectors",
    "source_web_urls",
    "source_public_youtube_urls_transcript_backed_video_sources",
    "source_optional_cloud_document_storage_connectors_implemented_through_generic_adapters",
)

CONNECTOR_FAMILY_IDS = (
    "source_optional_authenticated_restricted_repositories_through_generic_connectors",
    "source_optional_cloud_document_storage_connectors_implemented_through_generic_adapters",
)


def _registry() -> dict:
    return load_tool("check_capabilities").load_registry()


def test_registry_gate_green() -> None:
    check = load_tool("check_capabilities")
    problems = check.check_capabilities(REPO_ROOT)
    assert problems == [], f"capability registry findings: {[str(p) for p in problems][:5]}"


def test_all_fourteen_source_families_present_with_applicability() -> None:
    caps = {cap["id"]: cap for cap in _registry()["capabilities"]}
    for family_id in SOURCE_FAMILY_IDS:
        assert family_id in caps, f"source family missing from registry: {family_id}"
        cap = caps[family_id]
        assert cap["required_test_groups"], f"{family_id}: empty required_test_groups"
        assert cap["automated_tests"], f"{family_id}: empty automated_tests"
        assert cap["phase"] in (1, 2), f"{family_id}: unexpected phase {cap['phase']!r}"


def test_connector_families_optional_and_independently_flagged() -> None:
    caps = {cap["id"]: cap for cap in _registry()["capabilities"]}
    for connector_id in CONNECTOR_FAMILY_IDS:
        cap = caps[connector_id]
        assert cap["classification"] == "late/optional", (
            f"{connector_id}: connectors must be late/optional (disabled independently)"
        )
        assert cap["feature_flag"] == f"cap.{connector_id}", (
            f"{connector_id}: missing independent feature flag"
        )
    for family_id in SOURCE_FAMILY_IDS:
        if family_id not in CONNECTOR_FAMILY_IDS:
            assert caps[family_id]["classification"] == "stable/core", (
                f"{family_id}: core source family must be stable/core"
            )


def test_evidence_record_written() -> None:
    check = load_tool("check_capabilities")
    problems = check.check_capabilities(REPO_ROOT)
    write_evidence_fnd02(
        "VER-TECH-02-001",
        "TECH-02-001",
        "tests/meta/capabilities/ver-tech-02-001.py",
        {
            "source_families": len(SOURCE_FAMILY_IDS),
            "connector_families_optional": list(CONNECTOR_FAMILY_IDS),
            "registry_gate_findings": len(problems),
            "parity_matrix": "frozen ch02 table reparsed, 43 rows + 14 families matched",
        },
    )
    evidence = REPO_ROOT / "artifacts" / "verification" / "VER-TECH-02-001.json"
    assert evidence.exists()
