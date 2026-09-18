"""VER-ARCH-02-005 (ARCH-02-005): agentic outputs span the portable artifact set.

Oracle (should): agentic outputs support the common portable file classes
when renderers/providers support them. The registry carries the agentic
output families (reports, data tables, slide decks, infographics) each with
a nonempty automated test group — test applicability is derivable.
"""

from __future__ import annotations

from tests._evidence import REPO_ROOT
from tests.meta._evidence_fnd02 import write_evidence_fnd02
from tests.meta._tools import load_tool

AGENTIC_OUTPUT_FAMILIES = (
    "agentic_chat",
    "reports",
    "data_tables",
    "slide_decks",
    "infographics",
)


def test_agentic_output_families_present_with_test_groups() -> None:
    caps = {
        cap["id"]: cap for cap in load_tool("check_capabilities").load_registry()["capabilities"]
    }
    for family_id in AGENTIC_OUTPUT_FAMILIES:
        assert family_id in caps, f"agentic output family missing: {family_id}"
        cap = caps[family_id]
        assert cap["classification"] == "stable/core"
        assert cap["automated_tests"], f"{family_id}: no automated test groups"
        assert cap["required_test_groups"], f"{family_id}: no required test groups"


def test_evidence_record_written() -> None:
    write_evidence_fnd02(
        "VER-ARCH-02-005",
        "ARCH-02-005",
        "tests/meta/capabilities/ver-arch-02-005.py",
        {
            "agentic_output_families": list(AGENTIC_OUTPUT_FAMILIES),
            "all_stable_core_with_test_groups": True,
        },
    )
    evidence = REPO_ROOT / "artifacts" / "verification" / "VER-ARCH-02-005.json"
    assert evidence.exists()
