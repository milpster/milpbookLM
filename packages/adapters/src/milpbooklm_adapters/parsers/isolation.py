"""Parent-side subprocess isolation for untrusted source parsing."""

from __future__ import annotations

import os
import resource
import signal
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, assert_never

from milpbooklm_contracts.canonical_document import CanonicalDocument, JsonValue
from pydantic import BaseModel, ConfigDict

_CHILD_MODULE: Final = "milpbooklm_adapters.parsers.child"


@dataclass(frozen=True, slots=True)
class ParseLimits:
    """Kernel and wall-clock limits applied to every parser child."""

    cpu_seconds: int = 10
    memory_bytes: int = 512 * 1024 * 1024
    output_bytes: int = 32 * 1024 * 1024
    wall_seconds: float = 20.0


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
        self, source_version_id: uuid.UUID, media_type: str, data: bytes
    ) -> ParseResult:
        """Parse bytes through the isolated child and validate its result contract."""
        with tempfile.TemporaryDirectory(prefix="milpbooklm-parser-") as temp_name:
            temp = Path(temp_name)
            output = temp / "result.json"
            environment = {
                "HOME": temp_name,
                "PATH": os.environ.get("PATH", ""),
                "PYTHONHASHSEED": "0",
                "TMPDIR": temp_name,
            }
            process = subprocess.Popen(  # noqa: S603 - fixed interpreter/module argv
                [
                    sys.executable,
                    "-I",
                    "-m",
                    _CHILD_MODULE,
                    str(output),
                    str(source_version_id),
                    media_type,
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                cwd=temp,
                env=environment,
                preexec_fn=self._apply_limits,  # noqa: PLW1509 - required for POSIX RLIMITs
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

    def _apply_limits(self) -> None:
        resource.setrlimit(
            resource.RLIMIT_CPU, (self._limits.cpu_seconds, self._limits.cpu_seconds)
        )
        resource.setrlimit(
            resource.RLIMIT_AS, (self._limits.memory_bytes, self._limits.memory_bytes)
        )
        resource.setrlimit(
            resource.RLIMIT_FSIZE, (self._limits.output_bytes, self._limits.output_bytes)
        )


def _decode_envelope(envelope: _ChildEnvelope) -> ParseResult:  # noqa: PLR0911
    """Decode the child protocol into a typed parser result."""
    match envelope.state:
        case "succeeded":
            if envelope.document is None:
                return ParseFailure("internal", "parser child omitted the document")
            return ParseSuccess(CanonicalDocument.from_json(envelope.document))
        case "unsupported":
            return ParseFailure("unsupported", envelope.detail or "unsupported")
        case "corrupt":
            return ParseFailure("corrupt", envelope.detail or "corrupt")
        case "encrypted":
            return ParseFailure("encrypted", envelope.detail or "encrypted")
        case "too_large":
            return ParseFailure("too_large", envelope.detail or "too_large")
        case "timeout":
            return ParseFailure("timeout", envelope.detail or "timeout")
        case "policy_blocked":
            return ParseFailure("policy_blocked", envelope.detail or "policy_blocked")
        case "internal":
            return ParseFailure("internal", envelope.detail or "internal")
        case unreachable:
            assert_never(unreachable)
