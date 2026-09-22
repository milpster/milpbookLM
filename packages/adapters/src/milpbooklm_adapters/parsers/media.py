"""
Bounded audio/video probing via isolated ffprobe (ING-02c, sub-scope 23.2).

The container is probed with ffprobe as a bounded CLI child (JSON output,
capped time and bytes). Duration, track count, and container are checked
against declared limits. The canonical result is an ATTACHMENT node whose
locator carries millisecond time_range extent, plus an honest
``transcript_status`` metadata: STT is not deployed on this host, so media
without a lawfully available transcript reports ``unavailable`` — never a
success-empty transcript and never a fabricated one.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Final

from milpbooklm_contracts.canonical_document import (
    CanonicalDocument,
    CanonicalNode,
    NodeKind,
    ParserDescriptor,
    SourceLocator,
    canonical_document_id,
    canonical_node_id,
)

from .media_limits import (
    ALLOWED_MEDIA_CONTAINERS,
    MAX_MEDIA_DURATION_MS,
    MAX_MEDIA_TOOL_OUTPUT_BYTES,
    MAX_MEDIA_TOOL_TIMEOUT_SECONDS,
    MAX_MEDIA_TRACKS,
    MediaCorruptError,
    MediaTooLargeError,
    MediaUnsupportedError,
)

_PROFILE: Final = "ffprobe-bounded-v1"
_TRANSCRIPT_STATUS: Final = "unavailable"
_TRANSCRIPT_REASON: Final = "stt_not_deployed_on_host"


def parse_media(source_version_id: uuid.UUID, data: bytes, media_type: str) -> CanonicalDocument:
    """Probe one audio/video payload and emit a bounded, ms-located attachment."""
    probe = _probe(data)
    duration_ms = _duration_ms(probe)
    container = _container(probe)
    streams = _stream_summary(probe)
    parser = ParserDescriptor(
        identity="milpbooklm.media-probe",
        version="1",
        profile=_PROFILE,
        tool_versions=(f"ffprobe={_ffprobe_version()}",),
    )
    document_id = canonical_document_id(source_version_id, parser)
    root_id = canonical_node_id(document_id, "document")
    attachment_id = canonical_node_id(document_id, "attachment:1")
    attachment_text = (
        f"Media attachment: {container} container, "
        f"{duration_ms} ms duration, {len(streams)} track(s). "
        f"Transcript status: {_TRANSCRIPT_STATUS} ({_TRANSCRIPT_REASON})."
    )
    nodes = (
        CanonicalNode(
            node_id=root_id,
            kind=NodeKind.DOCUMENT,
            structural_identity="document",
            parent_id=None,
            child_order=0,
            text=None,
            locator=SourceLocator(path=("document",)),
        ),
        CanonicalNode(
            node_id=attachment_id,
            kind=NodeKind.ATTACHMENT,
            structural_identity="attachment:1",
            parent_id=root_id,
            child_order=1,
            text=attachment_text,
            locator=SourceLocator(
                path=("document", "attachment", "1"),
                extra_fields={
                    "time_ms_start": 0,
                    "time_ms_end": duration_ms,
                    "duration_ms": duration_ms,
                    "container": container,
                    "streams": [dict(stream) for stream in streams],
                },
            ),
        ),
    )
    return CanonicalDocument(
        document_id=document_id,
        source_version_id=source_version_id,
        mime_type=media_type,
        parser=parser,
        languages=(),
        metadata={
            "transcript_status": _TRANSCRIPT_STATUS,
            "transcript_reason": _TRANSCRIPT_REASON,
            "duration_ms": duration_ms,
            "container": container,
            "track_count": len(streams),
        },
        root_node_ids=(root_id,),
        nodes=nodes,
    )


_FFPROBE_VERSION_TOKEN: Final = 2


def _probe(data: bytes) -> dict[str, object]:
    """Run ffprobe as a bounded CLI child and parse its JSON report."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise MediaCorruptError("ffprobe binary is not available")
    with tempfile.TemporaryDirectory(prefix="milpbooklm-probe-") as temp_name:
        media_path = Path(temp_name) / "media.bin"
        media_path.write_bytes(data)
        try:
            process = subprocess.run(  # noqa: S603 - fixed argv, resolved binary
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-print_format",
                    "json",
                    "-show_format",
                    "-show_streams",
                    str(media_path),
                ],
                capture_output=True,
                timeout=MAX_MEDIA_TOOL_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise MediaCorruptError("ffprobe exceeded its time limit") from exc
        if process.returncode != 0:
            detail = process.stderr[:256].decode("utf-8", errors="replace")
            raise MediaCorruptError(f"ffprobe rejected the container: {detail.strip()[:128]}")
        if len(process.stdout) > MAX_MEDIA_TOOL_OUTPUT_BYTES:
            raise MediaTooLargeError("ffprobe report exceeded its size limit")
    try:
        report = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise MediaCorruptError("ffprobe report is not valid JSON") from exc
    if not isinstance(report, dict):
        raise MediaCorruptError("ffprobe report is malformed")
    return report


def _duration_ms(report: dict[str, object]) -> int:
    """Resolve whole-container duration in ms, bounded by the declared cap."""
    streams = report.get("streams")
    if not isinstance(streams, list) or not streams:
        raise MediaUnsupportedError("media has no decodable streams")
    duration = 0
    for stream in streams:
        if not isinstance(stream, dict):
            continue
        raw = stream.get("duration")
        if isinstance(raw, (int, float, str)) and str(raw).strip():
            try:
                duration = max(duration, int(float(raw) * 1000))
            except ValueError:
                continue
    if duration <= 0:
        raise MediaCorruptError("media duration is missing or zero")
    if duration > MAX_MEDIA_DURATION_MS:
        raise MediaTooLargeError(
            f"media duration {duration} ms exceeds the {MAX_MEDIA_DURATION_MS} ms limit"
        )
    return duration


def _container(report: dict[str, object]) -> str:
    """Name the container and enforce the allowlist before any further work."""
    fmt = report.get("format")
    if not isinstance(fmt, dict):
        raise MediaCorruptError("ffprobe report has no format section")
    name = fmt.get("format_name")
    if not isinstance(name, str) or name not in ALLOWED_MEDIA_CONTAINERS:
        raise MediaUnsupportedError(f"container {name!r} is outside the allowlist")
    return name


def _stream_summary(report: dict[str, object]) -> tuple[dict[str, str], ...]:
    """Summarize tracks (kind + codec) within the declared track cap."""
    streams = report.get("streams")
    if not isinstance(streams, list):
        raise MediaCorruptError("ffprobe report has no streams section")
    if len(streams) > MAX_MEDIA_TRACKS:
        raise MediaTooLargeError(f"media has {len(streams)} tracks, exceeding {MAX_MEDIA_TRACKS}")
    summary: list[dict[str, str]] = []
    for stream in streams:
        if not isinstance(stream, dict):
            continue
        codec = stream.get("codec_name")
        kind = stream.get("codec_type")
        summary.append(
            {
                "kind": str(kind) if isinstance(kind, str) else "unknown",
                "codec": str(codec) if isinstance(codec, str) else "unknown",
            }
        )
    return tuple(summary)


def _ffprobe_version() -> str:
    """Record the FFmpeg build for reproducibility (bounded probe)."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        return "ffprobe=missing"
    try:
        probe = subprocess.run(  # noqa: S603 - fixed argv, resolved binary
            [ffprobe, "-version"],
            capture_output=True,
            timeout=5,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "ffprobe=unknown"
    tokens = probe.stdout.decode("utf-8", errors="replace").splitlines()[0].split()
    if len(tokens) > _FFPROBE_VERSION_TOKEN:
        return f"ffprobe={tokens[_FFPROBE_VERSION_TOKEN]}"
    return "ffprobe=unknown"
