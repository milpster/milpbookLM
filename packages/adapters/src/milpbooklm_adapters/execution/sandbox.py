"""
Bubblewrap sandbox executor: the local-bubblewrap provider (EXE-01, guide/12).

The reviewed baseline isolation profile (arch ch12 §4), enforced here and
asserted by the escape suite:

* unprivileged user namespace + new PID/IPC/UTS/network/cgroup namespaces;
  nested user namespaces are DISABLED inside the sandbox
  (``--disable-userns --assert-userns-disabled`` — verified present in the
  host's bwrap 0.11.0);
* read-only runtime from the verified image rootfs; ``tmpfs`` ``/tmp`` and
  ``/run``; new ``procfs``; minimal ``/dev``; NO host home, host ``/etc``,
  host sockets or secrets are ever mounted;
* read-only inputs and one writable outputs directory under ``/workspace``
  at broker-generated safe paths (original filenames are metadata only);
* ``--clearenv`` plus a strict per-spec environment allowlist;
* ``--new-session`` (TTY injection defense) and ``--die-with-parent`` plus
  broker supervision: a per-execution cgroup v2 subtree (memory/CPU/pids)
  when the session delegates one, with ``cgroup.kill`` on timeout/cancel;
  otherwise SIGKILL of the sandbox's PID-namespace init (whose death tears
  down every namespace member) — and the capability gate reports such a
  host unavailable for model-driven execution anyway;
* no network interfaces by construction (unshared network namespace with
  nothing configured, and the launcher passes only the three std streams
  so no host socket or file descriptor crosses the boundary);
* seccomp is applied only where the kernel maintains it AND a reviewed
  filter has been curated for the runtime image; the host probe verifies
  filter installation for real (``Seccomp: 2`` under bwrap on this host),
  but no reviewed filter is curated for the prototype runtime image yet,
  so none is applied — recorded as a deferral, never faked;

OOM kills (cgroup ``memory.events``) and policy violations (spec or sandbox
setup refused) are DISTINCT terminal states from timeout kills and ordinary
failure. The bwrap executable is invoked by its probed, setuid-checked
absolute path; the argv below is broker-constructed exclusively from
broker-generated, symlink-free paths — no client string ever reaches the
bwrap command line except the spec argv executed INSIDE the sandbox.
"""

from __future__ import annotations

import contextlib
import io
import os
import re
import shutil
import signal
import subprocess
import threading
import time
import uuid
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Protocol, runtime_checkable

from milpbooklm_application.execution import (
    ExecutionHostPosture,
    ExecutionLimits,
    ExecutionOutcome,
    ExecutionRefusalCode,
    ExecutionRefusedError,
    ExecutionSpec,
    ExecutionStatus,
    ProducedOutput,
)

from milpbooklm_adapters.execution.cgroups import DelegatedCgroupController, ExecutionCgroup
from milpbooklm_adapters.execution.images import RuntimeImageStore
from milpbooklm_adapters.execution.outputs import OutputCollector, validate_declared_path

_ENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DIGEST_SHAPE = re.compile(r"^sha256:[0-9a-f]{64}$")
_BASE_ENV: dict[str, str] = {
    "PATH": "/usr/bin:/bin",
    "HOME": "/tmp",  # noqa: S108 - sandbox-internal tmpfs path, never the host /tmp
    "TMPDIR": "/tmp",  # noqa: S108 - sandbox-internal tmpfs path, never the host /tmp
}
_DRAIN_CHUNK = 4096
_WAIT_FLOOR_SECONDS = 0.05


class StagedInputReader(Protocol):
    """The narrow read service: staged blob IDs to bytes, nothing else."""

    def read(self, blob_id: uuid.UUID) -> bytes:
        """Return the finalized blob content (raises on unknown/corrupt)."""
        ...


class BubblewrapExecutionProvider:
    """The local-bubblewrap ExecutionProvider implementation."""

    def __init__(
        self,
        *,
        posture: ExecutionHostPosture,
        images: RuntimeImageStore,
        read_service: StagedInputReader,
        work_root: Path,
        collector: OutputCollector,
        cgroups: DelegatedCgroupController | None = None,
    ) -> None:
        """Wire verified host posture, image store, read service and roots."""
        self._posture = posture
        self._bwrap = posture.bwrap_path
        self._images = images
        self._read_service = read_service
        self._work_root = work_root
        self._collector = collector
        # Cgroup-mandatory posture: never silently degrade to the killpg
        # fallback while a delegated root is verified available.
        self._cgroups = cgroups
        if self._cgroups is None and posture.cgroup_root is not None:
            self._cgroups = DelegatedCgroupController(Path(posture.cgroup_root))
        self._work_root.mkdir(parents=True, exist_ok=True)

    def run(self, spec: ExecutionSpec) -> ExecutionOutcome:  # noqa: C901, PLR0912, PLR0915 - one supervised lifecycle, sequential by design
        """Execute one spec in the sandbox and return the bounded outcome."""
        if not self._posture.execution_available:
            raise ExecutionRefusedError(
                ExecutionRefusalCode.HOST_PREREQUISITES_UNSATISFIED,
                "; ".join(self._posture.notes) or "host prerequisites unsatisfied",
            )
        _validate_spec(spec)
        image = self._images.verify(spec.image_digest)
        execution_id = uuid.uuid4().hex[:16]
        work = self._work_root / f"exec-{execution_id}"
        inputs_dir = work / "inputs"
        outputs_dir = work / "outputs"
        inputs_dir.mkdir(parents=True)
        outputs_dir.mkdir(parents=True)
        started = time.monotonic()
        try:
            _stage_inputs(inputs_dir, spec, self._read_service)
            argv = _bwrap_argv(
                bwrap=self._bwrap,
                rootfs=image.rootfs,
                inputs_dir=inputs_dir,
                outputs_dir=outputs_dir,
                spec=spec,
            )
            stdout_buf: bytearray = bytearray()
            stderr_buf: bytearray = bytearray()
            with self._execution_cgroup(execution_id, spec.limits) as group:
                try:
                    process = subprocess.Popen(  # noqa: S603 - broker-built argv from the probed, setuid-checked bwrap path
                        argv,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        close_fds=True,
                        start_new_session=True,
                        # PLW1509: safe here — the hook is a 3-syscall cgroupfs
                        # write with no Python locks, and serving is sequential
                        # (drain threads start only after Popen returns).
                        preexec_fn=group.join_self if group is not None else None,  # noqa: PLW1509
                    )
                except OSError as exc:
                    return _policy_violation(
                        spec, started, f"sandbox launch failed: {exc.__class__.__name__}"
                    )
                readers = [
                    threading.Thread(
                        target=_drain_capped,
                        args=(stream, buffer_),
                        kwargs={"cap": cap},
                        daemon=True,
                    )
                    for stream, buffer_, cap in (
                        (process.stdout, stdout_buf, spec.limits.max_stdout_bytes),
                        (process.stderr, stderr_buf, spec.limits.max_stderr_bytes),
                    )
                ]
                for reader in readers:
                    reader.start()
                timed_out = False
                remaining = spec.limits.wall_timeout_seconds - (time.monotonic() - started)
                try:
                    process.wait(timeout=max(_WAIT_FLOOR_SECONDS, remaining))
                except subprocess.TimeoutExpired:
                    timed_out = True
                kill_method = "exit"
                if timed_out:
                    kill_method = _kill_tree(process, group)
                    process.wait()
                oom = group.oom_kill_count if group is not None else 0
            for reader in readers:
                reader.join(timeout=1.0)
            truncated = (
                len(stdout_buf) > spec.limits.max_stdout_bytes
                or len(stderr_buf) > spec.limits.max_stderr_bytes
            )
            wall = time.monotonic() - started
            stderr_bytes = bytes(stderr_buf[: spec.limits.max_stderr_bytes])
            if timed_out:
                status = ExecutionStatus.TIMEOUT_KILLED
            elif oom > 0:
                status = ExecutionStatus.OOM_KILLED
            elif process.returncode == 0:
                status = ExecutionStatus.SUCCEEDED
            elif stderr_bytes.startswith(b"bwrap: "):
                status = ExecutionStatus.POLICY_VIOLATION
            else:
                status = ExecutionStatus.FAILED
            outputs: tuple[ProducedOutput, ...] = ()
            undeclared = 0
            if status is ExecutionStatus.SUCCEEDED:
                try:
                    outputs, undeclared = self._collector.collect(
                        outputs_dir, spec.declared_outputs, spec.limits, execution_id
                    )
                except ExecutionRefusedError as exc:
                    return _policy_violation(
                        spec, started, f"output policy violation: {exc.code.value}"
                    )
            return ExecutionOutcome(
                status=status,
                exit_code=process.returncode,
                stdout_excerpt=bytes(stdout_buf[: spec.limits.max_stdout_bytes]),
                stderr_excerpt=stderr_bytes,
                outputs=outputs,
                wall_seconds=wall,
                oom_kill_count=oom,
                kill_method=kill_method,
                image_digest=spec.image_digest,
                truncated_streams=truncated,
                undeclared_output_count=undeclared,
            )
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def _execution_cgroup(
        self, execution_id: str, limits: ExecutionLimits
    ) -> AbstractContextManager[ExecutionCgroup | None]:
        """Open the per-execution cgroup, or a None-yielding no-op context."""
        if self._cgroups is None:
            return _NoCgroup()
        return self._cgroups.execution_cgroup(execution_id, limits)


class _NoCgroup:
    """No-op stand-in when no delegated cgroup root exists."""

    oom_kill_count = 0

    def __enter__(self) -> None:
        """Yield no cgroup."""
        return

    def __exit__(self, *exc_info: object) -> None:
        """Nothing to clean up."""


def _drain_capped(stream: io.BufferedReader | None, buffer_: bytearray, *, cap: int) -> None:
    """Drain one pipe fully, capturing only the first ``cap`` bytes."""
    if stream is None:  # pragma: no cover - both pipes are always wired
        return
    while chunk := stream.read(_DRAIN_CHUNK):
        if len(buffer_) < cap:
            buffer_.extend(chunk[: cap - len(buffer_)])


def _kill_tree(process: subprocess.Popen[bytes], group: object) -> str:
    """
    Kill the whole execution tree; return the honest method used.

    cgroup.kill is authoritative (kills every member atomically). The
    fallback SIGKILLs bwrap — the PID-namespace init — whose death makes
    the kernel kill every remaining namespace member; --die-with-parent is
    the independent backstop.
    """
    if isinstance(group, _CgroupLike):
        group.kill()
        return "cgroup.kill"
    with contextlib.suppress(OSError):
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    process.kill()
    return "namespace-init-kill"


@runtime_checkable
class _CgroupLike(Protocol):
    """The kill surface the executor needs from an execution cgroup."""

    def kill(self) -> None:
        """Kill every process in the subtree."""
        ...


def _validate_spec(spec: ExecutionSpec) -> None:
    """Refuse malformed specs before anything is staged (typed codes)."""
    if not _DIGEST_SHAPE.fullmatch(spec.image_digest):
        raise ExecutionRefusedError(ExecutionRefusalCode.UNKNOWN_IMAGE, "image digest is malformed")
    if not spec.argv or not all(isinstance(part, str) and part for part in spec.argv):
        raise ExecutionRefusedError(
            ExecutionRefusalCode.INVALID_SPEC, "argv must be a non-empty string tuple"
        )
    for key, value in spec.env_allowlist:
        if not _ENV_KEY.fullmatch(key) or not isinstance(value, str):
            raise ExecutionRefusedError(
                ExecutionRefusalCode.INVALID_SPEC, f"environment key {key!r} is not allowlistable"
            )
    for declared in spec.declared_outputs:
        validate_declared_path(declared.relative_path)
    limits = spec.limits
    if limits.wall_timeout_seconds <= 0 or limits.memory_max_bytes <= 0 or limits.pids_max <= 0:
        raise ExecutionRefusedError(ExecutionRefusalCode.INVALID_SPEC, "limits must be positive")


def _stage_inputs(inputs_dir: Path, spec: ExecutionSpec, read_service: StagedInputReader) -> int:
    """Re-resolve staged blob IDs into broker-named read-only input files."""
    total = 0
    for index, blob_id in enumerate(spec.input_blob_ids):
        try:
            data = read_service.read(blob_id)
        except Exception as exc:
            raise ExecutionRefusedError(
                ExecutionRefusalCode.UNKNOWN_STAGED_INPUT,
                f"staged input {index} could not be re-resolved ({exc.__class__.__name__})",
            ) from exc
        total += len(data)
        if total > spec.limits.max_staged_input_bytes:
            raise ExecutionRefusedError(
                ExecutionRefusalCode.STAGED_INPUT_TOO_LARGE,
                "staged inputs exceed the maximum staged size",
            )
        target = inputs_dir / f"input-{index:03d}.bin"
        with target.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        target.chmod(0o444)
    return total


def _bwrap_argv(
    *,
    bwrap: str,
    rootfs: Path,
    inputs_dir: Path,
    outputs_dir: Path,
    spec: ExecutionSpec,
) -> list[str]:
    """Build the full bwrap command line from broker-generated paths only."""
    argv: list[str] = [
        bwrap,
        "--unshare-user",
        "--unshare-pid",
        "--unshare-ipc",
        "--unshare-uts",
        "--unshare-net",
        "--unshare-cgroup",
        "--disable-userns",
        "--assert-userns-disabled",
        "--hostname",
        "exec-sandbox",
        "--ro-bind",
        str(rootfs / "usr"),
        "/usr",
        "--symlink",
        "usr/lib",
        "/lib",
        "--symlink",
        "usr/lib64",
        "/lib64",
        "--symlink",
        "usr/bin",
        "/bin",
        "--symlink",
        "usr/sbin",
        "/sbin",
        "--tmpfs",
        "/run",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--size",
        str(spec.limits.tmpfs_max_bytes),
        "--tmpfs",
        "/tmp",  # noqa: S108 - in-sandbox tmpfs mount point, not a host path
        "--tmpfs",
        "/workspace",
        "--ro-bind",
        str(inputs_dir),
        "/workspace/inputs",
        "--bind",
        str(outputs_dir),
        "/workspace/outputs",
        "--chdir",
        "/workspace",
        "--new-session",
        "--die-with-parent",
        "--clearenv",
    ]
    environment = {**_BASE_ENV, **dict(spec.env_allowlist)}
    for key in sorted(environment):
        argv.extend(("--setenv", key, environment[key]))
    etc = rootfs / "etc"
    if etc.is_dir():
        argv.extend(("--ro-bind", str(etc), "/etc"))
    argv.append("--")
    argv.extend(spec.argv)
    return argv


def _policy_violation(spec: ExecutionSpec, started: float, detail: str) -> ExecutionOutcome:
    """Build the POLICY_VIOLATION outcome (distinct from OOM/timeout/failure)."""
    return ExecutionOutcome(
        status=ExecutionStatus.POLICY_VIOLATION,
        exit_code=None,
        stdout_excerpt=b"",
        stderr_excerpt=detail.encode()[:1024],
        outputs=(),
        wall_seconds=time.monotonic() - started,
        oom_kill_count=0,
        kill_method="refused",
        image_digest=spec.image_digest,
    )
