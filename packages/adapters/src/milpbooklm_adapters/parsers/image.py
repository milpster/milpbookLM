"""
Bounded image ingestion with isolated Tesseract OCR (ING-02c).

Pixel and dimension limits are enforced from the image HEADER before any
pixel decode; OCR runs Tesseract as an isolated CLI child (deu+eng via
TESSDATA_PREFIX, bounded time and output) and emits one OCR-authority
paragraph per text line, each carrying a bounding-box region locator.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import PIL
from milpbooklm_contracts.canonical_document import (
    AuthorityClass,
    CanonicalDocument,
    CanonicalNode,
    NodeKind,
    ParserDescriptor,
    SourceLocator,
    canonical_document_id,
    canonical_node_id,
)
from PIL import Image

from .media_limits import (
    MAX_IMAGE_DIMENSION,
    MAX_IMAGE_PIXELS,
    MAX_OCR_OUTPUT_BYTES,
    MAX_OCR_TIMEOUT_SECONDS,
    OCR_LANGUAGES,
    ImageCorruptError,
    ImageTooLargeError,
    OcrEmptyError,
)

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

_PROFILE: Final = "tesseract-ocr-deu-eng-v1"
_TSV_LINE: Final = re.compile(
    r"^5\t(\d+)\t(\d+)\t(\d+)\t(\d+)\t(\d+)\t(\d+)\t(\d+)\t(\d+)\t(\d+)\t(-?\d+(?:\.\d+)?)\t(.*)$"
)


@dataclass(frozen=True, slots=True)
class _OcrLine:
    """One OCR text line with its bounding box (pixels, top-left origin)."""

    text: str
    bbox: tuple[float, float, float, float]


def parse_image(source_version_id: uuid.UUID, data: bytes) -> CanonicalDocument:
    """Bound-check, decode, OCR, and canonicalize one image payload."""
    image = _open_bounded(data)
    lines = _run_ocr(image)
    parser = ParserDescriptor(
        identity="milpbooklm.image-ocr",
        version="1",
        profile=_PROFILE,
        tool_versions=(f"tesseract={_tesseract_version()}", f"pillow={PIL.__version__}"),
    )
    document_id = canonical_document_id(source_version_id, parser)
    root_id = canonical_node_id(document_id, "document")
    nodes = [
        CanonicalNode(
            node_id=root_id,
            kind=NodeKind.DOCUMENT,
            structural_identity="document",
            parent_id=None,
            child_order=0,
            text=None,
            locator=SourceLocator(
                path=("document",),
                extra_fields={
                    "width_px": image.width,
                    "height_px": image.height,
                    "format": image.format,
                },
            ),
        )
    ]
    for number, line in enumerate(lines, start=1):
        identity = f"ocr-line:{number}"
        nodes.append(
            CanonicalNode(
                node_id=canonical_node_id(document_id, identity),
                kind=NodeKind.PARAGRAPH,
                structural_identity=identity,
                parent_id=root_id,
                child_order=number,
                text=line.text,
                locator=SourceLocator(
                    path=("document", "ocr-line", str(number)),
                    bbox=line.bbox,
                ),
                authority=AuthorityClass.OCR,
            )
        )
    return CanonicalDocument(
        document_id=document_id,
        source_version_id=source_version_id,
        mime_type=_mime_for(image.format),
        parser=parser,
        languages=("de", "en"),
        metadata={"ocr_languages": OCR_LANGUAGES, "ocr_lines": len(lines)},
        root_node_ids=(root_id,),
        nodes=tuple(nodes),
    )


def _open_bounded(data: bytes) -> Image.Image:
    """Header-check, apply dimension/pixel caps BEFORE decode, then load."""
    try:
        image = Image.open(io.BytesIO(data))
    except (OSError, ValueError) as exc:
        raise ImageCorruptError("image header is not decodable") from exc
    width, height = image.size
    if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
        raise ImageTooLargeError(
            f"image dimension {width}x{height} exceeds {MAX_IMAGE_DIMENSION}px limit"
        )
    if width * height > MAX_IMAGE_PIXELS:
        raise ImageTooLargeError(
            f"image has {width * height} pixels, exceeding the {MAX_IMAGE_PIXELS} limit"
        )
    try:
        image.load()
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ImageCorruptError("image body is not decodable") from exc
    return image


def _run_ocr(image: Image.Image) -> tuple[_OcrLine, ...]:
    """Run Tesseract as a bounded CLI child and collect word groups as lines."""
    tesseract = shutil.which("tesseract")
    if tesseract is None:
        raise ImageCorruptError("tesseract binary is not available")
    with tempfile.TemporaryDirectory(prefix="milpbooklm-ocr-") as temp_name:
        image_path = Path(temp_name) / "frame.png"
        image.save(image_path, format="PNG")
        environment = {"PATH": os.environ.get("PATH", "")}
        if tessdata_prefix := os.environ.get("TESSDATA_PREFIX"):
            environment["TESSDATA_PREFIX"] = tessdata_prefix
        try:
            process = subprocess.run(  # noqa: S603 - fixed argv, resolved binary
                [
                    tesseract,
                    str(image_path),
                    "stdout",
                    "-l",
                    OCR_LANGUAGES,
                    "tsv",
                ],
                capture_output=True,
                timeout=MAX_OCR_TIMEOUT_SECONDS,
                env=environment,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ImageCorruptError("tesseract exceeded its time limit") from exc
        if process.returncode != 0:
            detail = process.stderr[:256].decode("utf-8", errors="replace")
            raise ImageCorruptError(f"tesseract failed: {detail.strip()[:128]}")
        if len(process.stdout) > MAX_OCR_OUTPUT_BYTES:
            raise ImageCorruptError("tesseract output exceeded its limit")
    return _lines_from_tsv(process.stdout)


def _lines_from_tsv(raw: bytes) -> tuple[_OcrLine, ...]:
    """Group TSV word rows (level 5) into lines with the union bounding box."""
    lines: dict[tuple[int, int, int, int], list[tuple[str, float, float, float, float]]] = {}
    for line in raw.decode("utf-8", errors="replace").splitlines():
        match = _TSV_LINE.match(line)
        if match is None:
            continue
        left, top, width, height, conf, text = match.groups()[5:]
        if float(conf) < 0 or not text.strip():
            continue
        groups = match.groups()
        key = (int(groups[0]), int(groups[1]), int(groups[2]), int(groups[3]))
        lines.setdefault(key, []).append(
            (text.strip(), float(left), float(top), float(width), float(height))
        )
    ordered: list[_OcrLine] = []
    for (page, block, paragraph, line_number), words in sorted(
        lines.items(), key=lambda item: (item[0][0], item[0][1], item[0][2], item[0][3])
    ):
        del page, block, paragraph, line_number
        text = " ".join(word[0] for word in words)
        left = min(word[1] for word in words)
        top = min(word[2] for word in words)
        right = max(word[1] + word[3] for word in words)
        bottom = max(word[2] + word[4] for word in words)
        ordered.append(_OcrLine(text, (left, top, right, bottom)))
    if not ordered:
        raise OcrEmptyError("OCR produced no text")
    return tuple(ordered)


def _tesseract_version() -> str:
    """Record the Tesseract build for reproducibility (bounded probe)."""
    tesseract = shutil.which("tesseract")
    if tesseract is None:
        return "tesseract=missing"
    try:
        probe = subprocess.run(  # noqa: S603 - resolved system binary, fixed argv
            [tesseract, "--version"],
            capture_output=True,
            timeout=5,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "tesseract=unknown"
    first_line = (probe.stderr or probe.stdout).decode("utf-8", errors="replace").splitlines()
    match = re.match(r"tesseract\s+(\S+)", first_line[0]) if first_line else None
    return match.group(1) if match else "unknown"


def _mime_for(pillow_format: str | None) -> str:
    return {
        "PNG": "image/png",
        "JPEG": "image/jpeg",
        "GIF": "image/gif",
        "WEBP": "image/webp",
        "BMP": "image/bmp",
    }.get(pillow_format or "", "image/png")
