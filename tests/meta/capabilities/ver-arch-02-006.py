"""VER-ARCH-02-006 (ARCH-02-006): portable file classes gate on renderers.

Oracle (should): portable file classes are supported when the installed
renderers/providers support them. Slide decks and infographics declare the
renderer dependency, so their file-class obligations activate only with a
healthy renderer — the gating is visible in the registry, not assumed.
"""

from __future__ import annotations

from tests._evidence import REPO_ROOT
from tests.meta._evidence_fnd02 import write_evidence_fnd02
from tests.meta._tools import load_tool

# Slide decks and infographics are frozen at parity phase 5 (renderer-gated).
RENDERER_GATED_PHASE = 5


def _caps() -> dict[str, dict]:
    return {
        cap["id"]: cap for cap in load_tool("check_capabilities").load_registry()["capabilities"]
    }


def test_renderer_gated_families_declare_the_renderer_dependency() -> None:
    caps = _caps()
    for renderer_family in ("slide_decks", "infographics"):
        cap = caps[renderer_family]
        assert "renderer" in cap["dependencies"], (
            f"{renderer_family}: file-class output must gate on a renderer dependency"
        )
        assert cap["phase"] == RENDERER_GATED_PHASE, (
            f"{renderer_family}: phase drifted to {cap['phase']!r}"
        )


def test_renderer_unhealthy_disables_the_capability() -> None:
    effective = load_tool("effective_state")
    cap = _caps()["slide_decks"]
    compiled = {**cap, "implemented": True, "enabled": True}
    policy = effective.CapabilityPolicy(
        allow_external_providers=True,
        enabled_feature_flags=frozenset({str(cap["feature_flag"])}),
    )
    with_renderer = effective.compute_effective_state(
        compiled, policy=policy, dependency_health=dict.fromkeys(cap["dependencies"], True)
    )
    without_renderer = effective.compute_effective_state(
        compiled,
        policy=policy,
        dependency_health={dep: (dep != "renderer") for dep in cap["dependencies"]},
    )
    assert with_renderer.enabled is True
    assert without_renderer.enabled is False
    assert "renderer" in without_renderer.reason


def test_evidence_record_written() -> None:
    write_evidence_fnd02(
        "VER-ARCH-02-006",
        "ARCH-02-006",
        "tests/meta/capabilities/ver-arch-02-006.py",
        {
            "renderer_gated_families": ["slide_decks", "infographics"],
            "renderer_unhealthy": "capability disabled with dependency reason",
        },
    )
    evidence = REPO_ROOT / "artifacts" / "verification" / "VER-ARCH-02-006.json"
    assert evidence.exists()
