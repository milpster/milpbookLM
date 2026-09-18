"""VER-TECH-00-001 (TECH-00-001): every normative occurrence is classified.

Oracle: every normative occurrence is classified and its decision invariant
holds. The frozen ledger's fingerprints are recomputed from source/term/
occurrence/statement (generator contract formula) and every ID/classification
is re-validated; the TAD decision registry is present.
"""

from __future__ import annotations

import importlib.util
import sys
import types

from tests._evidence import REPO_ROOT, write_evidence

GUIDE = REPO_ROOT / "milpbookml-implementation-guide"
LEDGER = GUIDE / "requirements.generated.json"
EXTRACTOR = REPO_ROOT / "tools" / "spec" / "extract_requirements.py"
DECISIONS = GUIDE / "00-status-decisions.md"

# Frozen ledger size (FND-01 baseline; a change means the spec was regenerated).
EXPECTED_LEDGER_SIZE = 507


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


def test_ledger_fingerprints_and_classifications_re_derive() -> None:
    extractor = _load_extractor()
    violations = extractor.check_ledger(LEDGER)
    assert violations == [], f"ledger violations: {[str(v) for v in violations][:5]}"
    count = len(extractor.json.loads(LEDGER.read_text())["requirements"])
    assert count == EXPECTED_LEDGER_SIZE, f"frozen ledger size changed: {count}"


def test_decision_registry_present() -> None:
    text = DECISIONS.read_text()
    missing = [f"TAD-{n:03d}" for n in range(1, 13) if f"| TAD-{n:03d} |" not in text]
    assert missing == [], f"missing frozen decisions: {missing}"


def test_evidence_record_written() -> None:
    extractor = _load_extractor()
    violations = extractor.check_ledger(LEDGER)
    write_evidence(
        "VER-TECH-00-001",
        "TECH-00-001",
        "tests/meta/normative_extraction/ver-tech-00-001.py",
        {
            "ledger_requirements": EXPECTED_LEDGER_SIZE,
            "violations": len(violations),
            "fingerprint_formula": (
                "SHA-256(source + LF + term + LF + occurrence_on_line + LF + normalized statement)"
            ),
            "tad_registry": "TAD-001..TAD-012 present in 00-status-decisions.md",
        },
    )
    evidence = REPO_ROOT / "artifacts" / "verification" / "VER-TECH-00-001.json"
    assert evidence.exists()
