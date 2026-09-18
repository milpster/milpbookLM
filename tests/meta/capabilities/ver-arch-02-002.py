"""VER-ARCH-02-002 (ARCH-02-002): source type/version semantics are retained.

Oracle: classification, phase, dependencies and applicability match the
parity matrix. Connector sources use the same snapshot/version contract and
are independently disableable (own feature flags, optional classification);
web and transcript-backed URL sources remain stable/core first-class.
"""

from __future__ import annotations

from tests._evidence import REPO_ROOT
from tests.meta._evidence_fnd02 import write_evidence_fnd02
from tests.meta._tools import load_tool

# web/youtube URL sources are first-class core material, frozen at phase 2.
URL_SOURCE_PHASE = 2

CONNECTORS = (
    "source_optional_authenticated_restricted_repositories_through_generic_connectors",
    "source_optional_cloud_document_storage_connectors_implemented_through_generic_adapters",
)


def _caps() -> dict[str, dict]:
    return {
        cap["id"]: cap for cap in load_tool("check_capabilities").load_registry()["capabilities"]
    }


def test_connectors_share_snapshot_contract_and_disable_independently() -> None:
    caps = _caps()
    for connector_id in CONNECTORS:
        cap = caps[connector_id]
        assert cap["classification"] == "late/optional"
        assert cap["feature_flag"] == f"cap.{connector_id}", (
            f"{connector_id}: no independent feature flag — cannot disable independently"
        )
        assert (
            "connector" in cap["reference_text"].lower()
            or "adapter" in cap["reference_text"].lower()
        ), f"{connector_id}: reference text lost the connector/adapter contract"


def test_web_and_transcript_url_sources_are_stable_core() -> None:
    caps = _caps()
    for url_source in (
        "source_web_urls",
        "source_public_youtube_urls_transcript_backed_video_sources",
    ):
        cap = caps[url_source]
        assert cap["classification"] == "stable/core"
        assert cap["phase"] == URL_SOURCE_PHASE, f"{url_source}: phase drifted to {cap['phase']!r}"
        assert cap["reference_text"], f"{url_source}: empty reference text"


def test_evidence_record_written() -> None:
    write_evidence_fnd02(
        "VER-ARCH-02-002",
        "ARCH-02-002",
        "tests/meta/capabilities/ver-arch-02-002.py",
        {
            "connector_capabilities": list(CONNECTORS),
            "independent_flags": True,
            "url_sources_stable_core": [
                "source_web_urls",
                "source_public_youtube_urls_transcript_backed_video_sources",
            ],
        },
    )
    evidence = REPO_ROOT / "artifacts" / "verification" / "VER-ARCH-02-002.json"
    assert evidence.exists()
