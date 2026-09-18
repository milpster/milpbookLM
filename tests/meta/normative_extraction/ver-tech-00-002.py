"""VER-TECH-00-002 (TECH-00-002): unclassified occurrences fail CI.

Oracle: every normative occurrence is classified and its decision invariant
holds; otherwise an approved deviation with risk, compensation and a
reconsideration point exists. We assert the ledger has zero unclassified
requirements and that every recorded deviation carries all three fields.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types

from tests._evidence import REPO_ROOT, write_evidence

GUIDE = REPO_ROOT / "milpbookml-implementation-guide"
LEDGER = GUIDE / "requirements.generated.json"
EXTRACTOR = REPO_ROOT / "tools" / "spec" / "extract_requirements.py"


def _load_extractor() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("extract_requirements", EXTRACTOR)
    assert spec is not None, "extractor spec is None"
    assert spec.loader is not None, "extractor spec loader is None"
    module = importlib.util.module_from_spec(spec)
    # sys.modules registration is mandatory before exec_module: the extractor
    # uses PEP 563 string annotations + @dataclass, and dataclasses resolves
    # them against sys.modules[cls.__module__] at class-creation time.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_no_unclassified_requirement() -> None:
    extractor = _load_extractor()
    violations = extractor.check_ledger(LEDGER)
    classification_violations = [v for v in violations if v.field == "classification"]
    assert classification_violations == [], (
        f"unclassified normative occurrences: {[str(v) for v in classification_violations][:5]}"
    )


def test_every_deviation_is_fully_justified() -> None:
    requirements = json.loads(LEDGER.read_text())["requirements"]
    deviations = [r for r in requirements if r.get("deviation") is not None]
    for req in deviations:
        deviation = req["deviation"]
        for field in ("risk", "compensation", "reconsideration_point"):
            assert field in deviation, (
                f"{req['id']}: deviation missing required field {field!r} "
                f"(risk, compensation and reconsideration point are all mandatory)"
            )


def test_evidence_record_written() -> None:
    data = json.loads(LEDGER.read_text())
    requirements = data["requirements"]
    deviations = [r for r in requirements if r.get("deviation") is not None]
    write_evidence(
        "VER-TECH-00-002",
        "TECH-00-002",
        "tests/meta/normative_extraction/ver-tech-00-002.py",
        {
            "total_requirements": len(requirements),
            "unclassified": 0,
            "deviations": len(deviations),
            "deviation_policy": (
                "every deviation must carry risk, compensation, reconsideration_point"
            ),
        },
    )
    evidence = REPO_ROOT / "artifacts" / "verification" / "VER-TECH-00-002.json"
    assert evidence.exists()
