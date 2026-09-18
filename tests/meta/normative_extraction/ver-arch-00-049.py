"""VER-ARCH-00-049 (ARCH-00-049): builds publish a complete conformance profile.

Oracle: the machine-readable profile identifies implemented, enabled,
disabled-optional, provisional and deliberate-non-target behavior plus
dependencies; a stable/core capability is never not_applicable; enabling
optional code activates its tests; provisional/non-target behavior is never
advertised.
"""

from __future__ import annotations

import json

from tests._evidence import REPO_ROOT
from tests.meta._evidence_fnd02 import write_evidence_fnd02

CONFORMANCE = REPO_ROOT / "artifacts" / "conformance.json"
# The frozen ch02 parity matrix + source families + deliberate non-targets.
REGISTRY_CAPABILITIES = 61
CLASSIFICATIONS = (
    "stable/core",
    "advanced/provider-dependent",
    "late/optional",
    "provisional/announced",
    "deliberate-non-target",
)


def _doc() -> dict:
    assert CONFORMANCE.exists(), (
        "artifacts/conformance.json missing — run `uv run python tools/spec/emit_conformance.py`"
    )
    return json.loads(CONFORMANCE.read_text(encoding="utf-8"))


def test_profile_identifies_all_five_behavior_classes() -> None:
    doc = _doc()
    present = {cap["classification"] for cap in doc["capabilities"]}
    assert present == set(CLASSIFICATIONS), (
        f"missing behavior classes: {set(CLASSIFICATIONS) - present}"
    )
    assert len(doc["capabilities"]) == REGISTRY_CAPABILITIES


def test_stable_core_never_not_applicable() -> None:
    doc = _doc()
    offenders = [
        cap["id"]
        for cap in doc["capabilities"]
        if cap["classification"] == "stable/core"
        and cap["implementation_status"] == "not_applicable"
    ]
    assert offenders == [], f"stable/core marked not_applicable: {offenders}"


def test_enabling_a_capability_activates_its_tests() -> None:
    doc = _doc()
    for cap in doc["capabilities"]:
        assert cap["automated_tests"], (
            f"{cap['id']}: no automated tests — applicability not derivable"
        )
    for cap in doc["capabilities"]:
        if cap["effective"]:
            assert cap["enabled"], f"{cap['id']}: effective without being enabled"
            assert cap["implementation_status"] == "implemented", (
                f"{cap['id']}: effective without implemented state"
            )


def test_provisional_and_non_target_never_advertised() -> None:
    doc = _doc()
    advertised = set(doc["advertised"])
    for cap in doc["capabilities"]:
        if cap["classification"] in (
            "provisional/announced",
            "deliberate-non-target",
            "late/optional",
        ):
            assert cap["id"] not in advertised, (
                f"{cap['id']}: provisional/optional/non-target advertised"
            )
    assert doc["advertised"] == [], "nothing may be advertised while nothing is effective"


def test_evidence_record_written() -> None:
    doc = _doc()
    by_class: dict[str, int] = {}
    for cap in doc["capabilities"]:
        by_class[cap["classification"]] = by_class.get(cap["classification"], 0) + 1
    write_evidence_fnd02(
        "VER-ARCH-00-049",
        "ARCH-00-049",
        "tests/meta/normative_extraction/ver-arch-00-049.py",
        {
            "capabilities": len(doc["capabilities"]),
            "by_classification": by_class,
            "advertised": doc["advertised"],
            "invariants": [
                "five behavior classes identified",
                "stable/core never not_applicable",
                "effective implies implemented+enabled (tests active)",
                "provisional/non-target/optional never advertised",
            ],
        },
    )
    evidence = REPO_ROOT / "artifacts" / "verification" / "VER-ARCH-00-049.json"
    assert evidence.exists()
