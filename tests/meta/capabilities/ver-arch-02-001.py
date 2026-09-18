"""VER-ARCH-02-001 (ARCH-02-001): the architecture supports every source family.

Oracle: classification, phase, dependencies and applicability match the
parity matrix. The frozen Chapter 02 source-family list (14 families) is
fully present in the capability registry, one entry per family.
"""

from __future__ import annotations

from tests._evidence import REPO_ROOT
from tests.meta._evidence_fnd02 import write_evidence_fnd02
from tests.meta._tools import load_tool

# Frozen ch02 counts; drift here means the frozen table itself changed.
PARITY_MATRIX_ROWS = 43
SOURCE_FAMILIES = 14


def test_every_frozen_source_family_has_a_registry_entry() -> None:
    check = load_tool("check_capabilities")
    rows, families = check.parse_frozen_chapter()
    registry = check.load_registry()["capabilities"]
    by_name = {check._normalize(cap["name"]): cap for cap in registry}
    for family in families:
        key = check._normalize(family)
        assert key in by_name, f"frozen source family absent from registry: {family!r}"
        cap = by_name[key]
        assert cap["dependencies"], f"{family}: family has no declared dependencies"
        assert len(rows) == PARITY_MATRIX_ROWS, f"parity matrix row count changed: {len(rows)}"
        assert len(families) == SOURCE_FAMILIES, f"source family count changed: {len(families)}"


def test_no_family_entry_is_duplicated() -> None:
    check = load_tool("check_capabilities")
    problems = check.check_capabilities(REPO_ROOT)
    duplicates = [p for p in problems if "duplicated" in p.kind]
    assert duplicates == [], f"duplicated rows/families: {[str(p) for p in duplicates]}"


def test_evidence_record_written() -> None:
    check = load_tool("check_capabilities")
    _, families = check.parse_frozen_chapter()
    write_evidence_fnd02(
        "VER-ARCH-02-001",
        "ARCH-02-001",
        "tests/meta/capabilities/ver-arch-02-001.py",
        {
            "source_families": len(families),
            "registry_entries": len(check.load_registry()["capabilities"]),
            "gate_findings": len(check.check_capabilities(REPO_ROOT)),
        },
    )
    evidence = REPO_ROOT / "artifacts" / "verification" / "VER-ARCH-02-001.json"
    assert evidence.exists()
