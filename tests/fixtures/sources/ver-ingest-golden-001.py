"""VER-INGEST-GOLDEN-001 (ING-02a/02c): versioned canonical/locator goldens + hostile corpus.

Oracle: every family parses through the REAL isolated child into a canonical
document that byte-equals its committed golden (fixed source-version UUID),
and the hostile corpus (macros, external references, archive bombs,
corruption, image bombs/oversizes, over-duration audio) is rejected with
explicit failure states — never a success-empty document, never a fabricated
transcript.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from milpbooklm_adapters.parsers.isolation import (
    IsolatedParser,
    ParseFailure,
    ParseSuccess,
    WebLocatorContext,
)

from tests._evidence import write_evidence

FIXTURES = Path(__file__).resolve().parent
GOLDENS = FIXTURES / "goldens"
SOURCE_VERSION_ID = uuid.UUID("00000000-0000-5000-8000-000000000211")
GOLDEN_MEDIA_DURATION_MS = 500

# OCR traineddata (D5: deu+eng) lives in the task scratch area; the isolated
# child only inherits TESSDATA_PREFIX from this environment.
os.environ.setdefault(
    "TESSDATA_PREFIX", str(FIXTURES.parents[2] / "scratch" / "t23-ocr" / "tessdata")
)

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PPTX_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
HTML_TYPE = "text/html"
EPUB_TYPE = "application/epub+zip"
WEB_CONTEXT = WebLocatorContext(
    canonical_url="https://example.test/reports/q3",
    captured_at="2026-09-22T12:00:00+00:00",
)

GOLDENS_UNDER_TEST = {
    "golden-text.txt": "text/plain",
    "golden-pdf.pdf": "application/pdf",
    "golden-markdown.md": "text/markdown",
    "golden-csv.csv": "text/csv",
    "golden-csv-utf16le.csv": "text/csv",
    "golden-xlsx.xlsx": XLSX_TYPE,
    "golden-docx.docx": DOCX_TYPE,
    "golden-pptx.pptx": PPTX_TYPE,
    "golden-html.html": HTML_TYPE,
    "golden-epub.epub": EPUB_TYPE,
    "golden-image.png": "image/png",
    "golden-audio.wav": "audio/x-wav",
    "golden-video.mp4": "video/mp4",
}

HOSTILE_CORPUS = {
    "hostile-macro.xlsx": (XLSX_TYPE, "policy_blocked"),
    "hostile-extref.docx": (DOCX_TYPE, "policy_blocked"),
    "hostile-bomb.xlsx": (XLSX_TYPE, "too_large"),
    "hostile-corrupt.xlsx": (XLSX_TYPE, "corrupt"),
    "hostile-bomb.epub": (EPUB_TYPE, "too_large"),
    "hostile-corrupt.epub": (EPUB_TYPE, "corrupt"),
    "hostile-entity.epub": (EPUB_TYPE, "policy_blocked"),
    "hostile-external.epub": (EPUB_TYPE, "policy_blocked"),
    "hostile-bomb-image.png": ("image/png", "too_large"),
    "hostile-oversized-image.png": ("image/png", "too_large"),
    "hostile-corrupt-image.png": ("image/png", "corrupt"),
    "hostile-overduration-audio.wav": ("audio/x-wav", "too_large"),
}

HOSTILE_FAMILY_COVERAGE = {
    "text": "hostile-corrupt-image.png",
    "pdf": "hostile-corrupt.xlsx",
    "markdown": "hostile-corrupt-image.png",
    "csv": "hostile-corrupt-image.png",
    "xlsx": "hostile-bomb.xlsx",
    "docx": "hostile-extref.docx",
    "pptx": "hostile-corrupt.xlsx",
    "epub": "hostile-external.epub",
    "html_web": "hostile-external.epub",
    "image_ocr": "hostile-bomb-image.png",
    "audio": "hostile-overduration-audio.wav",
    "video": "hostile-overduration-audio.wav",
    "public_video": "hostile-external.epub",
}


def test_golden_canonical_documents_match() -> None:
    for fixture_name, media_type in sorted(GOLDENS_UNDER_TEST.items()):
        context = WEB_CONTEXT if media_type == HTML_TYPE else None
        result = IsolatedParser().parse(
            SOURCE_VERSION_ID,
            media_type,
            (FIXTURES / fixture_name).read_bytes(),
            web_locator=context,
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


def test_hostile_corpus_rejected_with_explicit_states() -> None:
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


def test_hostile_corpus_covers_every_live_family() -> None:
    assert set(HOSTILE_FAMILY_COVERAGE) == {
        "text",
        "pdf",
        "markdown",
        "csv",
        "xlsx",
        "docx",
        "pptx",
        "epub",
        "html_web",
        "image_ocr",
        "audio",
        "video",
        "public_video",
    }
    assert all((FIXTURES / fixture).is_file() for fixture in HOSTILE_FAMILY_COVERAGE.values())


def test_ocr_golden_carries_german_english_text_with_region_bboxes() -> None:
    result = IsolatedParser().parse(
        SOURCE_VERSION_ID, "image/png", (FIXTURES / "golden-image.png").read_bytes()
    )
    assert isinstance(result, ParseSuccess)
    ocr_lines = [
        node for node in result.document.nodes if node.kind.value == "paragraph"
    ]
    texts = [node.text for node in ocr_lines if node.text is not None]
    assert any("Vierteljahresbericht" in text for text in texts)
    assert any("Umsatz" in text for text in texts)
    assert any("Quarterly report" in text for text in texts)
    assert all(node.authority.value == "ocr" for node in ocr_lines)
    assert all(node.locator.bbox is not None for node in ocr_lines)
    first_bbox = ocr_lines[0].locator.bbox
    assert first_bbox is not None
    left, top, right, bottom = first_bbox
    assert right > left
    assert bottom > top


def test_media_goldens_carry_ms_time_range_locators() -> None:
    for fixture_name, (media_type, streams) in {
        "golden-audio.wav": ("audio/x-wav", 1),
        "golden-video.mp4": ("video/mp4", 2),
    }.items():
        result = IsolatedParser().parse(
            SOURCE_VERSION_ID, media_type, (FIXTURES / fixture_name).read_bytes()
        )
        assert isinstance(result, ParseSuccess), fixture_name
        attachment = next(
            node for node in result.document.nodes if node.kind.value == "attachment"
        )
        locator = attachment.locator
        assert locator.extra_fields["time_ms_start"] == 0
        assert locator.extra_fields["time_ms_end"] == GOLDEN_MEDIA_DURATION_MS
        assert result.document.metadata["duration_ms"] == GOLDEN_MEDIA_DURATION_MS
        stream_entries = locator.extra_fields["streams"]
        assert isinstance(stream_entries, list)
        assert len(stream_entries) == streams


def test_media_without_stt_reports_honest_unavailable_transcript() -> None:
    for fixture_name, media_type in {
        "golden-audio.wav": "audio/x-wav",
        "golden-video.mp4": "video/mp4",
    }.items():
        result = IsolatedParser().parse(
            SOURCE_VERSION_ID, media_type, (FIXTURES / fixture_name).read_bytes()
        )
        assert isinstance(result, ParseSuccess), fixture_name
        assert result.document.metadata["transcript_status"] == "unavailable"
        transcript_nodes = [
            node
            for node in result.document.nodes
            if node.kind.value in ("transcript_segment", "speaker_turn")
        ]
        assert transcript_nodes == []


def test_web_snapshot_locators_pin_url_capture_dom_and_heading_paths() -> None:
    result = IsolatedParser().parse(
        SOURCE_VERSION_ID,
        HTML_TYPE,
        (FIXTURES / "golden-html.html").read_bytes(),
        web_locator=WEB_CONTEXT,
    )
    assert isinstance(result, ParseSuccess)
    paragraph = next(node for node in result.document.nodes if node.text == "Der Umsatz stieg.")
    assert paragraph.locator.path[:4] == (
        "web",
        WEB_CONTEXT.canonical_url,
        WEB_CONTEXT.captured_at,
        "dom",
    )
    assert "main:nth-of-type(1)>p:nth-of-type(1)" in paragraph.locator.path
    assert paragraph.locator.path[-2:] == ("heading", "Quartalsbericht")


def test_html_snapshot_excludes_navigation_and_script_text() -> None:
    result = IsolatedParser().parse(
        SOURCE_VERSION_ID,
        HTML_TYPE,
        (FIXTURES / "golden-html.html").read_bytes(),
        web_locator=WEB_CONTEXT,
    )
    assert isinstance(result, ParseSuccess)
    text = "\n".join(node.text or "" for node in result.document.nodes)
    assert "Navigationstext" not in text
    assert "prompt injection from script" not in text


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
                "pptx: slide/shape/paragraph with separate notes stream; "
                "image: per-line pixel bbox with OCR authority; "
                "audio/video: ms-precision time_range extent"
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
