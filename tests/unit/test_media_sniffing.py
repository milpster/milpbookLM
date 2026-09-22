"""Bounded media sniffing matrix for the ING-02a families."""

from __future__ import annotations

from pathlib import Path

from milpbooklm_adapters.parsers.sniffing import sniff_media_type
from milpbooklm_domain.acquisition import IdentifiedMedia

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "sources"
TEXT_SAMPLE_BYTES = 4096


def test_pdf_magic_wins_over_other_prefixes() -> None:
    assert sniff_media_type(b"%PDF-1.7 rest") is IdentifiedMedia.PDF


def test_office_families_identified_by_zip_part_markers() -> None:
    base = b"PK\x03\x04" + b"\x00" * 20 + b"[Content_Types].xml"
    assert sniff_media_type(base + b" xl/workbook.xml") is IdentifiedMedia.XLSX
    assert sniff_media_type(base + b" word/document.xml") is IdentifiedMedia.DOCX
    assert sniff_media_type(base + b" ppt/presentation.xml") is IdentifiedMedia.PPTX
    assert sniff_media_type(base + b" application/epub+zip") is IdentifiedMedia.EPUB


def test_unknown_zip_is_unsupported() -> None:
    assert sniff_media_type(b"PK\x03\x04" + b"plain-zip-without-office-parts") is None


def test_text_families_classified_by_content() -> None:
    markdown = b"# Heading\n\n- item one\n- item two\n"
    csv_like = b"name,city\nAnna,Berlin\nBen,Wien\n"
    plain = b"Just an ordinary paragraph of prose text.\n"
    assert sniff_media_type(markdown) is IdentifiedMedia.MARKDOWN
    assert sniff_media_type(csv_like) is IdentifiedMedia.CSV
    assert sniff_media_type(plain) is IdentifiedMedia.TEXT


def test_html_identified_by_document_structure() -> None:
    payload = b"<!doctype html><html><body>Atlas</body></html>"
    assert sniff_media_type(payload) is IdentifiedMedia.HTML


def test_image_families_identified_by_magic() -> None:
    assert sniff_media_type(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32) is IdentifiedMedia.IMAGE_PNG
    assert sniff_media_type(b"\xff\xd8\xff\xe0" + b"\x00" * 32) is IdentifiedMedia.IMAGE_JPEG
    assert sniff_media_type(b"GIF89a" + b"\x00" * 32) is IdentifiedMedia.IMAGE_GIF
    assert sniff_media_type(b"GIF87a" + b"\x00" * 32) is IdentifiedMedia.IMAGE_GIF
    assert sniff_media_type(b"BM" + b"\x00" * 32) is IdentifiedMedia.IMAGE_BMP
    assert (
        sniff_media_type(b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 24)
        is IdentifiedMedia.IMAGE_WEBP
    )


def test_audio_video_families_identified_by_magic() -> None:
    assert sniff_media_type(b"RIFF\x00\x00\x00\x00WAVE" + b"\x00" * 24) is (
        IdentifiedMedia.AUDIO_WAV
    )
    assert sniff_media_type(b"ID3\x03\x00\x00\x00" + b"\x00" * 24) is IdentifiedMedia.AUDIO_MP3
    assert sniff_media_type(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 24) is (
        IdentifiedMedia.VIDEO_MP4
    )
    assert sniff_media_type(b"\x1a\x45\xdf\xa3" + b"\x00" * 32) is IdentifiedMedia.VIDEO_WEBM


def test_boms_are_handled_and_binary_rejected() -> None:
    assert sniff_media_type("name,city\r\nAnna,Berlin\r\n".encode("utf-16")) is (
        IdentifiedMedia.CSV
    )
    assert sniff_media_type("﻿\ufeff# Title\n\n- one\n- two\n".encode("utf-8")) is (
        IdentifiedMedia.MARKDOWN
    )
    assert sniff_media_type(b"\x00\x01\x02binary") is None
    unpaired_surrogates = b"\xff\xfe\x00\xd8\x00\xd8"
    assert sniff_media_type(unpaired_surrogates) is None


def test_sniffing_is_bounded_to_the_declared_sample() -> None:
    prose = b"Plain prose paragraphs without structure. " * 128
    assert len(prose) > TEXT_SAMPLE_BYTES
    assert sniff_media_type(prose + b"\n\n# Heading beyond the sample\n") is (
        IdentifiedMedia.TEXT
    )
    assert sniff_media_type(b"") is None


def test_committed_golden_fixtures_sniff_to_their_families() -> None:
    expectations = {
        "golden-markdown.md": IdentifiedMedia.MARKDOWN,
        "golden-csv.csv": IdentifiedMedia.CSV,
        "golden-csv-utf16le.csv": IdentifiedMedia.CSV,
        "golden-xlsx.xlsx": IdentifiedMedia.XLSX,
        "golden-docx.docx": IdentifiedMedia.DOCX,
        "golden-pptx.pptx": IdentifiedMedia.PPTX,
        "golden-html.html": IdentifiedMedia.HTML,
        "golden-epub.epub": IdentifiedMedia.EPUB,
        "golden-image.png": IdentifiedMedia.IMAGE_PNG,
        "golden-audio.wav": IdentifiedMedia.AUDIO_WAV,
        "golden-video.mp4": IdentifiedMedia.VIDEO_MP4,
    }
    for name, expected in expectations.items():
        assert sniff_media_type((FIXTURES / name).read_bytes()) is expected, name
