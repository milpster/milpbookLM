"""VER-TECH-00-003 (TECH-00-003): builds emit a valid conformance.json.

Oracle: each build emits conformance.json with capability ID, classification,
implementation status, enabled state, dependencies and test lists; stable/core
capabilities are never not_applicable; disabled optional features stay visible
and unadvertised.
"""

from __future__ import annotations

import json

from tests._evidence import REPO_ROOT, write_evidence

CONFORMANCE = REPO_ROOT / "artifacts" / "conformance.json"
VALID_STATUSES = {"not_started", "in_progress", "implemented", "not_applicable"}


REQUIRED_FIELDS = (
    "id",
    "classification",
    "implementation_status",
    "enabled",
    "dependencies",
    "automated_tests",
    "manual_tests",
)


def _load() -> dict:
    message = (
        "artifacts/conformance.json missing — "
        "run `uv run python tools/spec/emit_conformance.py` (CI does this)"
    )
    assert CONFORMANCE.exists(), message
    return json.loads(CONFORMANCE.read_text())


def test_conformance_shape_complete() -> None:
    doc = _load()
    assert doc["schema_version"] == 1
    capabilities = doc["capabilities"]
    assert isinstance(capabilities, list)
    assert capabilities, "conformance.json has no capabilities"
    for cap in capabilities:
        for field in REQUIRED_FIELDS:
            message = f"capability {cap.get('id')!r} missing field {field!r}"
            assert field in cap, message
        assert cap["implementation_status"] in VALID_STATUSES
        assert isinstance(cap["enabled"], bool)


def test_stable_core_never_not_applicable() -> None:
    doc = _load()
    offenders = [
        cap["id"]
        for cap in doc["capabilities"]
        if cap["classification"] == "stable/core"
        and cap["implementation_status"] == "not_applicable"
    ]
    message = f"stable/core capabilities marked not_applicable: {offenders}"
    assert offenders == [], message


def test_disabled_optionals_not_advertised() -> None:
    doc = _load()
    advertised = set(doc.get("advertised", []))
    for cap in doc["capabilities"]:
        if not cap["enabled"]:
            message = (
                f"disabled capability {cap['id']!r} is advertised — "
                "must remain visible as disabled only"
            )
            assert cap["id"] not in advertised, message


def test_evidence_record_written() -> None:
    doc = _load()
    write_evidence(
        "VER-TECH-00-003",
        "TECH-00-003",
        "tests/meta/normative_extraction/ver-tech-00-003.py",
        {
            "conformance_path": "artifacts/conformance.json",
            "capabilities": len(doc["capabilities"]),
            "advertised": doc.get("advertised", []),
            "invariants": [
                "shape complete",
                "stable/core never not_applicable",
                "disabled optionals not advertised",
            ],
        },
    )
    evidence = REPO_ROOT / "artifacts" / "verification" / "VER-TECH-00-003.json"
    assert evidence.exists()
