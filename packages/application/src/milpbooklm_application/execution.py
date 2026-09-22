"""
Execution provider port for isolated code execution (EXE-01, guide/12).

Higher layers target this typed port only; the initial provider is
``local-bubblewrap`` and no higher-level feature may depend on
Bubblewrap-specific arguments (arch ch12 §2). The spec carries staged blob
IDs - never host paths - and the provider (through the broker) re-resolves
inputs itself under broker-generated safe paths. Outcomes distinguish OOM
kills, policy violations and timeout kills from ordinary success/failure
(guide/12 resources: "Record OOM and policy violations distinctly").

The refusal crossing async deadline scopes must stay hand-written (T26
lesson: dataclass-generated frozen exceptions break under contextlib
unwinding), so :class:`ExecutionRefusedError` follows the T26/T28 pattern.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol


class ExecutionRefusalCode(StrEnum):
    """Stable broker/provider refusal classes (never content-bearing)."""

    UNSIGNED_SPEC = "unsigned_spec"
    BAD_SIGNATURE = "bad_signature"
    NONCE_REPLAY = "nonce_replay"
    NONCE_STALE = "nonce_stale"
    MALFORMED_FRAME = "malformed_frame"
    UNKNOWN_PROTOCOL_VERSION = "unknown_protocol_version"
    UNKNOWN_PEER = "unknown_peer"
    UNKNOWN_IMAGE = "unknown_image"
    IMAGE_VERIFICATION_FAILED = "image_verification_failed"
    UNKNOWN_STAGED_INPUT = "unknown_staged_input"
    STAGED_INPUT_TOO_LARGE = "staged_input_too_large"
    INVALID_SPEC = "invalid_spec"
    HOST_PREREQUISITES_UNSATISFIED = "host_prerequisites_unsatisfied"
    OUTPUT_POLICY_VIOLATION = "output_policy_violation"
    PUBLISH_AUTHZ_DENIED = "publish_authz_denied"
    BROKER_UNAVAILABLE = "broker_unavailable"
    PROTOCOL_TRANSPORT = "protocol_transport"


class ExecutionRefusedError(Exception):
    """
    An execution request was refused before or during sandboxing (typed failure).

    Hand-written (no dataclass machinery): the refusal can cross async
    deadline scopes during unwinding (T26 lesson). Fields stay immutable by
    convention; nothing reassigns them.
    """

    __slots__ = ("code", "detail")

    def __init__(self, code: ExecutionRefusalCode, detail: str) -> None:
        """Bind the stable refusal code and a safe, content-free detail."""
        super().__init__(code, detail)
        self.code = code
        self.detail = detail

    def __str__(self) -> str:
        """Return the stable code and safe detail."""
        return f"{self.code.value}: {self.detail}"


class ExecutionStatus(StrEnum):
    """Terminal execution states; OOM, policy and timeout are distinct."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMEOUT_KILLED = "timeout_killed"
    OOM_KILLED = "oom_killed"
    POLICY_VIOLATION = "policy_violation"


@dataclass(frozen=True, slots=True)
class ExecutionLimits:
    """Resource envelope for one execution (arch ch12 §5, all mandatory)."""

    wall_timeout_seconds: float = 30.0
    memory_max_bytes: int = 512 * 1024 * 1024
    pids_max: int = 128
    cpu_quota_micros: int = 200_000
    cpu_period_micros: int = 100_000
    tmpfs_max_bytes: int = 64 * 1024 * 1024
    max_stdout_bytes: int = 64 * 1024
    max_stderr_bytes: int = 64 * 1024
    max_staged_input_bytes: int = 256 * 1024 * 1024
    max_output_file_bytes: int = 64 * 1024 * 1024
    max_total_output_bytes: int = 256 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class DeclaredOutput:
    """One declared output: a safe relative path under /workspace/outputs."""

    relative_path: str
    max_bytes: int


@dataclass(frozen=True, slots=True)
class ExecutionSpec:
    """
    One execution request (signed + nonce-bound on the wire).

    Carries only IDs, argv and an environment allowlist - never host paths or
    mount directives (guide/04: "never accepts host paths or arbitrary mount
    directives"). Staged inputs are blob IDs re-resolved by the broker.
    """

    image_digest: str
    argv: tuple[str, ...]
    env_allowlist: tuple[tuple[str, str], ...] = ()
    input_blob_ids: tuple[uuid.UUID, ...] = ()
    declared_outputs: tuple[DeclaredOutput, ...] = ()
    limits: ExecutionLimits = field(default_factory=ExecutionLimits)
    nonce: str = ""


@dataclass(frozen=True, slots=True)
class ProducedOutput:
    """One collected output: validated, quarantined, content-typed by bytes."""

    declared_path: str
    content_sha256: str
    size_bytes: int
    sniffed_media: str
    quarantine_path: str
    blob_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class ExecutionOutcome:
    """The full observable result of one sandboxed execution."""

    status: ExecutionStatus
    exit_code: int | None
    stdout_excerpt: bytes
    stderr_excerpt: bytes
    outputs: tuple[ProducedOutput, ...]
    wall_seconds: float
    oom_kill_count: int
    kill_method: str
    image_digest: str
    truncated_streams: bool = False
    undeclared_output_count: int = 0


@dataclass(frozen=True, slots=True)
class ExecutionHostPosture:
    """
    Verified host facts for the local-bubblewrap provider (arch ch12 §11).

    ``execution_available`` is the fail-closed gate: a setuid-marked bwrap,
    a missing user namespace or absent cgroup/memory hard boundary reports
    the capability unavailable rather than running with weaker isolation.
    """

    bwrap_path: str
    bwrap_version: str | None
    bwrap_setuid: bool
    userns_supported: bool
    seccomp_supported: bool
    kernel_release: str
    cgroup_root: str | None
    cgroup_controllers: tuple[str, ...]
    notes: tuple[str, ...] = ()

    @property
    def execution_available(self) -> bool:
        """True only when every mandatory prerequisite is verified."""
        return bool(
            self.bwrap_version
            and not self.bwrap_setuid
            and self.userns_supported
            and self.cgroup_root is not None
            and "cpu" in self.cgroup_controllers
            and "memory" in self.cgroup_controllers
            and "pids" in self.cgroup_controllers
        )


class ExecutionProvider(Protocol):
    """The provider seam: immutable spec in, typed outcome out (guide/12)."""

    def run(self, spec: ExecutionSpec) -> ExecutionOutcome:
        """Execute one spec in isolation and return the bounded outcome."""
        ...
