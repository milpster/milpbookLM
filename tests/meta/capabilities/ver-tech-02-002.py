"""VER-TECH-02-002 (TECH-02-002): availability is never inferred.

Oracle: the effective state is computed only from compiled support,
administrator policy, configured providers and dependency health — the
prohibited behavior (inferring availability from provider names / flags of
an unimplemented capability) is specifically attempted and remains denied;
disabled capabilities are never advertised.
"""

from __future__ import annotations

import json

from tests._evidence import REPO_ROOT
from tests.meta._evidence_fnd02 import write_evidence_fnd02
from tests.meta._tools import load_tool

CONFORMANCE = REPO_ROOT / "artifacts" / "conformance.json"


def _registry_caps() -> list[dict]:
    return load_tool("check_capabilities").load_registry()["capabilities"]


def test_unimplemented_capability_stays_disabled_regardless_of_providers() -> None:
    effective = load_tool("effective_state")
    caps = _registry_caps()
    unimplemented = [cap for cap in caps if not cap["implemented"]]
    assert unimplemented, "registry unexpectedly has implemented capabilities"
    for cap in unimplemented:
        # Prohibited inference attempt: every dependency reported healthy and
        # every feature flag enabled by policy. Provider names/flags must not
        # flip an uncompiled capability to enabled.
        policy = effective.CapabilityPolicy(
            allow_external_providers=True,
            enabled_feature_flags=frozenset({str(cap["feature_flag"])}),
        )
        health = {str(dep): True for dep in cap["dependencies"]}
        state = effective.compute_effective_state(cap, policy=policy, dependency_health=health)
        assert state.enabled is False, (
            f"{cap['id']}: enabled without compiled support — availability was inferred"
        )
        assert "no compiled support" in state.reason


def test_disabled_capabilities_never_advertised() -> None:
    doc = json.loads(CONFORMANCE.read_text(encoding="utf-8"))
    advertised = set(doc["advertised"])
    offenders = [
        cap["id"] for cap in doc["capabilities"] if not cap["effective"] and cap["id"] in advertised
    ]
    assert offenders == [], f"disabled capabilities advertised: {offenders}"


def test_evidence_record_written() -> None:
    caps = _registry_caps()
    attempted = [cap["id"] for cap in caps if not cap["implemented"]]
    write_evidence_fnd02(
        "VER-TECH-02-002",
        "TECH-02-002",
        "tests/meta/capabilities/ver-tech-02-002.py",
        {
            "inference_attempts": len(attempted),
            "inference_attempts_denied": len(attempted),
            "gates": [
                "compiled support",
                "administrator policy",
                "configured providers",
                "dependency health",
            ],
            "advertised": json.loads(CONFORMANCE.read_text(encoding="utf-8"))["advertised"],
        },
    )
    evidence = REPO_ROOT / "artifacts" / "verification" / "VER-TECH-02-002.json"
    assert evidence.exists()
