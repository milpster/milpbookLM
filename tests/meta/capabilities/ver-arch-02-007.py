"""VER-ARCH-02-007 (ARCH-02-007): the full parity matrix is matched.

Oracle: classification, phase, dependencies and applicability match the
parity matrix. The complete frozen Chapter 02 table (43 matrix rows + 14
source families) plus the four deliberate non-targets exactly covers the 61
registry entries; every row's classification follows its baseline priority.
"""

from __future__ import annotations

from tests._evidence import REPO_ROOT
from tests.meta._evidence_fnd02 import write_evidence_fnd02
from tests.meta._tools import load_tool

# 43 matrix rows + 14 source families + 4 deliberate non-targets.
REGISTRY_ENTRIES = 61


def test_registry_exactly_covers_frozen_table_plus_non_targets() -> None:
    check = load_tool("check_capabilities")
    registry = check.load_registry()["capabilities"]
    rows, families = check.parse_frozen_chapter()
    expected = len(rows) + len(families) + len(check.NON_TARGET_IDS)
    assert len(registry) == expected == REGISTRY_ENTRIES, (
        f"registry size {len(registry)} != {len(rows)} rows + {len(families)} families + "
        f"{len(check.NON_TARGET_IDS)} non-targets"
    )
    assert len({cap["id"] for cap in registry}) == REGISTRY_ENTRIES, "registry ids are not unique"


def test_every_row_classification_follows_baseline_priority() -> None:
    check = load_tool("check_capabilities")
    problems = check.check_capabilities(REPO_ROOT)
    mismatches = [p for p in problems if p.kind in ("classification_mismatch", "priority_unmapped")]
    assert mismatches == [], f"priority/classification drift: {[str(p) for p in mismatches]}"


def test_full_registry_gate_is_green() -> None:
    check = load_tool("check_capabilities")
    problems = check.check_capabilities(REPO_ROOT)
    assert problems == [], f"registry findings: {[str(p) for p in problems][:5]}"


def test_evidence_record_written() -> None:
    check = load_tool("check_capabilities")
    rows, families = check.parse_frozen_chapter()
    write_evidence_fnd02(
        "VER-ARCH-02-007",
        "ARCH-02-007",
        "tests/meta/capabilities/ver-arch-02-007.py",
        {
            "matrix_rows": len(rows),
            "source_families": len(families),
            "deliberate_non_targets": len(check.NON_TARGET_IDS),
            "registry_entries": 61,
            "gate_findings": 0,
        },
    )
    evidence = REPO_ROOT / "artifacts" / "verification" / "VER-ARCH-02-007.json"
    assert evidence.exists()
