"""VER-INGEST-GOLDEN-001 (ING-02a): versioned canonical/locator goldens + hostile corpus.

Oracle: every ING-02a family parses through the REAL isolated child into a
canonical document that byte-equals its committed golden (fixed source-version
UUID), and the hostile office corpus (macros, external references, archive
bombs, corruption) is rejected with explicit failure states — never a
success-empty document, never macro/external-reference execution.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from milpbooklm_adapters.parsers.isolation import (
    IsolatedParser,
    ParseFailure,
    ParseSuccess,
)

from tests._evidence import write_evidence

FIXTURES = Path(__file__).resolve().parent
GOLDENS = FIXTURES / "goldens"
SOURCE_VERSION_ID = uuid.UUID("00000000-0000-5000-8000-000000000211")

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PPTX_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

GOLDENS_UNDER_TEST = {
    "golden-markdown.md": "text/markdown",
    "golden-csv.csv": "text/csv",
    "golden-csv-utf16le.csv": "text/csv",
    "golden-xlsx.xlsx": XLSX_TYPE,
    "golden-docx.docx": DOCX_TYPE,
    "golden-pptx.pptx": PPTX_TYPE,
}

HOSTILE_CORPUS = {
    "hostile-macro.xlsx": (XLSX_TYPE, "policy_blocked"),
    "hostile-extref.docx": (DOCX_TYPE, "policy_blocked"),
    "hostile-bomb.xlsx": (XLSX_TYPE, "too_large"),
    "hostile-corrupt.xlsx": (XLSX_TYPE, "corrupt"),
}


def test_golden_canonical_documents_match() -> None:
    for fixture_name, media_type in sorted(GOLDENS_UNDER_TEST.items()):
        result = IsolatedParser().parse(
            SOURCE_VERSION_ID, media_type, (FIXTURES / fixture_name).read_bytes()
        )
        assert isinstance(result, ParseSuccess), f"{fixture_name}: {result}"
        golden_path = GOLDENS / f"{Path(fixture_name).stem}.canonical.json"
        golden = json.loads(golden_path.read_text())
        assert result.document.to_json() == golden, f"{fixture_name} drifted from golden"


def test_xlsx_stores_formulas_and_cached_values_distinctly() -> None:
    result = IsolatedParser().parse(
        SOURCE_VERSION_ID, XLSX_TYPE, (FIXTURES / "golden-xlsx.xlsx").read_bytes()
    )
    assert isinstance(result, ParseSuccess)
    cells = {n.structural_identity: n for n in result.document.nodes if n.kind.value == "cell"}
    formula_cell = cells["sheet:Daten:table:1:row:4:cell:B4"]
    assert formula_cell.text == "40"
    assert formula_cell.extra_fields == {"formula": "=B2-B3"}
    plain_cell = cells["sheet:Daten:table:1:row:2:cell:B2"]
    assert plain_cell.text == "120"
    assert plain_cell.extra_fields == {}
    assert result.document.parser.extra_fields == {
        "formula_policy": "stored_not_evaluated",
        "recalculation": "none",
    }


def test_pptx_keeps_speaker_notes_a_separate_stream() -> None:
    result = IsolatedParser().parse(
        SOURCE_VERSION_ID, PPTX_TYPE, (FIXTURES / "golden-pptx.pptx").read_bytes()
    )
    assert isinstance(result, ParseSuccess)
    notes = [n for n in result.document.nodes if n.locator.path[3:4] == ("notes",)]
    assert [n.text for n in notes] == ["Sprechernotiz: Umsatz hervorheben."]
    shape_texts = [n.text for n in result.document.nodes if n.locator.path[3:4] == ("shape",)]
    assert "Sprechernotiz: Umsatz hervorheben." not in shape_texts


def test_office_locators_carry_sheet_slide_row_col_guarantees() -> None:
    result = IsolatedParser().parse(
        SOURCE_VERSION_ID, XLSX_TYPE, (FIXTURES / "golden-xlsx.xlsx").read_bytes()
    )
    assert isinstance(result, ParseSuccess)
    cell = next(
        n for n in result.document.nodes if n.structural_identity.endswith("cell:B2")
    )
    row_b2 = 2
    col_b2 = 2
    assert cell.locator.extra_fields["sheet"] == "Daten"
    assert cell.locator.extra_fields["cell_ref"] == "B2"
    assert cell.locator.extra_fields["row"] == row_b2
    assert cell.locator.extra_fields["col"] == col_b2
    assert cell.locator.path == ("document", "sheet", "Daten", "cell", "B2")


def test_hostile_office_corpus_rejected_with_explicit_states() -> None:
    outcomes: dict[str, str] = {}
    for fixture_name, (media_type, expected) in sorted(HOSTILE_CORPUS.items()):
        result = IsolatedParser().parse(
            SOURCE_VERSION_ID, media_type, (FIXTURES / fixture_name).read_bytes()
        )
        assert isinstance(result, ParseFailure), f"{fixture_name} unexpectedly parsed"
        assert result.state == expected, f"{fixture_name}: {result.state} != {expected}"
        assert result.detail, f"{fixture_name}: failure carries no detail"
        outcomes[fixture_name] = result.state
    assert set(outcomes.values()) <= {"policy_blocked", "too_large", "corrupt"}


def test_evidence_record_written() -> None:
    write_evidence(
        "VER-INGEST-GOLDEN-001",
        "ARCH-06-family-subset",
        "tests/fixtures/sources/ver-ingest-golden-001.py",
        {
            "golden_families": sorted(GOLDENS_UNDER_TEST),
            "locator_guarantees": (
                "markdown: char spans over NFC/LF text; csv: row/col structural; "
                "xlsx: sheet name + A1 cell refs + row/col; docx: block/row/col; "
                "pptx: slide/shape/paragraph with separate notes stream"
            ),
            "formula_policy": (
                "cached values as text, formulas as distinct extra field; never evaluated"
            ),
            "hostile_corpus": {
                name: state for name, (_, state) in sorted(HOSTILE_CORPUS.items())
            },
            "macro_execution": (
                "none - vbaProject.bin and external links are rejected before any "
                "parser library loads"
            ),
        },
    )
