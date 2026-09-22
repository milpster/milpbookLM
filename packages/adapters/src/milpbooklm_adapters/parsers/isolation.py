"""Parent-side subprocess isolation for untrusted source parsing."""

from __future__ import annotations

import json
import os
import resource
import signal
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Final, Literal

from milpbooklm_contracts.canonical_document import CanonicalDocument, JsonValue
from pydantic import BaseModel, ConfigDict

from .parser_context import WebLocatorContext

_CHILD_MODULE: Final = "milpbooklm_adapters.parsers.child"


_MEDIA_PREFIXES: Final = ("image/", "audio/", "video/")


@dataclass(frozen=True, slots=True)
class ParseLimits:
    """Kernel and wall-clock limits applied to every parser child."""

    cpu_seconds: int = 10
    memory_bytes: int = 512 * 1024 * 1024
    output_bytes: int = 32 * 1024 * 1024
    wall_seconds: float = 20.0
    # Native probe/OCR children (ffprobe/tesseract) map gigabytes of virtual
    # address space at startup while using little resident memory, so media
    # types get a separate, larger RLIMIT_AS than pure-Python parser children.
    media_memory_bytes: int = 3 * 1024 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ParseSuccess:
    """A validated canonical document returned by the isolated child."""

    document: CanonicalDocument


@dataclass(frozen=True, slots=True)
class ParseFailure:
    """An explicit source parse failure; no substitute document exists."""

    state: Literal[
        "unsupported",
        "corrupt",
        "encrypted",
        "too_large",
        "timeout",
        "policy_blocked",
        "no_content",
        "internal",
    ]
    detail: str


type ParseResult = ParseSuccess | ParseFailure


class _ChildEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: Literal[
        "succeeded",
        "unsupported",
        "corrupt",
        "encrypted",
        "too_large",
        "timeout",
        "policy_blocked",
        "no_content",
        "internal",
    ]
    document: dict[str, JsonValue] | None = None
    detail: str | None = None


class IsolatedParser:
    """Execute parsers in a separate rootless process with no writable shared temp."""

    def __init__(self, limits: ParseLimits | None = None) -> None:
        """Bind fixed limits for every child invocation."""
        self._limits: ParseLimits = limits or ParseLimits()

    @property
    def limits(self) -> ParseLimits:
        """Expose the active profile for operational evidence."""
        return self._limits

    def parse(
        self,
        source_version_id: uuid.UUID,
        media_type: str,
        data: bytes,
        *,
        web_locator: WebLocatorContext | None = None,
    ) -> ParseResult:
        """Parse bytes through the isolated child and validate its result contract."""
        with tempfile.TemporaryDirectory(prefix="milpbooklm-parser-") as temp_name:
            temp = Path(temp_name)
            output = temp / "result.json"
            context_path = temp / "context.json"
            context_path.write_text(
                json.dumps(
                    {
                        "canonical_url": web_locator.canonical_url,
                        "captured_at": web_locator.captured_at,
                    }
                    if web_locator is not None
                    else {}
                ),
                encoding="utf-8",
            )
            environment = {
                "HOME": temp_name,
                "PATH": os.environ.get("PATH", ""),
                "PYTHONHASHSEED": "0",
                "TMPDIR": temp_name,
            }
            # OCR traineddata lives outside the child sandbox (D5: deu+eng);
            # the parent's TESSDATA_PREFIX is the only additional variable passed.
            if tessdata_prefix := os.environ.get("TESSDATA_PREFIX"):
                environment["TESSDATA_PREFIX"] = tessdata_prefix
            process = subprocess.Popen(  # noqa: S603 - fixed interpreter/module argv
                [
                    sys.executable,
                    "-I",
                    "-m",
                    _CHILD_MODULE,
                    str(output),
                    str(source_version_id),
                    media_type,
                    str(context_path),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                cwd=temp,
                env=environment,
                # POSIX RLIMITs require preexec_fn; the worker loop is single-threaded
                preexec_fn=partial(self._apply_limits, self._limit_for(media_type)),  # noqa: PLW1509
            )
            try:
                _, stderr = process.communicate(data, timeout=self._limits.wall_seconds)
            except subprocess.TimeoutExpired:
                process.kill()
                _ = process.communicate()
                return ParseFailure("timeout", "parser exceeded wall-clock limit")
            return self._completed_result(process.returncode, stderr, output)

    def _completed_result(self, returncode: int, stderr: bytes, output: Path) -> ParseResult:
        if returncode != 0 or not output.is_file():
            detail = stderr[:512].decode("utf-8", errors="replace") or "parser child failed"
            if returncode in {-signal.SIGXFSZ, 128 + signal.SIGXFSZ}:
                return ParseFailure("too_large", detail)
            return ParseFailure("internal", detail)
        if output.stat().st_size > self._limits.output_bytes:
            return ParseFailure("too_large", "parser output exceeded limit")
        return _decode_envelope(_ChildEnvelope.model_validate_json(output.read_bytes()))

    def _limit_for(self, media_type: str) -> int:
        if media_type.startswith(_MEDIA_PREFIXES):
            return self._limits.media_memory_bytes
        return self._limits.memory_bytes

    def _apply_limits(self, memory_bytes: int) -> None:
        resource.setrlimit(
            resource.RLIMIT_CPU, (self._limits.cpu_seconds, self._limits.cpu_seconds)
        )
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
        resource.setrlimit(
            resource.RLIMIT_FSIZE, (self._limits.output_bytes, self._limits.output_bytes)
        )


def _decode_envelope(envelope: _ChildEnvelope) -> ParseResult:
    """Decode the child protocol into a typed parser result."""
    if envelope.state == "succeeded":
        if envelope.document is None:
            return ParseFailure("internal", "parser child omitted the document")
        return ParseSuccess(CanonicalDocument.from_json(envelope.document))
    return ParseFailure(envelope.state, envelope.detail or envelope.state)
