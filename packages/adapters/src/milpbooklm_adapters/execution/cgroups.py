"""
Per-execution cgroup v2 subtree control (EXE-01, guide/12 resources).

Linux cgroups are the hard boundary for memory/CPU/process lifetime. This
controller discovers the session-delegated writable cgroup root (systemd
delegates ``user@<uid>.service`` to the user; on the reference host the
literal ``user.slice/user-<uid>.slice/cgroup.subtree_control`` file is
root-owned but the delegated ``app.slice`` subtree is fully user-writable),
creates one subtree per execution with ``memory.max``/``pids.max``/``cpu.max``
limits, moves the sandbox process in, reports OOM kills from
``memory.events`` (distinct from policy violations), and kills the whole
subtree via ``cgroup.kill`` on timeout/cancel.

When no delegated root exists the controller reports ``None`` and the
executor falls back to SIGKILL of the sandbox PID-namespace init; the
capability gate (host posture) then reports execution unavailable on such a
host - isolation is never weakened to make a host pass.

Writes to ``cgroup.subtree_control`` go one controller at a time: the
kernel on the reference host rejects the combined "+a +b +c" form with
EINVAL even though the syntax is documented.
"""

from __future__ import annotations

import contextlib
import errno
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Final

from milpbooklm_application.execution import ExecutionLimits

CGROUP_FS = Path("/sys/fs/cgroup")
EXEC_SLICE_NAME: Final = "milpbooklm-exec.slice"
_QUOTA_FLOOR_MICROS: Final = 1000  # kernel rejects quota/period values below 1000


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _write(path: Path, value: str) -> None:
    with path.open("w", encoding="utf-8") as handle:
        handle.write(value)


def discover_delegated_cgroup_root() -> tuple[str | None, tuple[str, ...], list[str]]:
    """
    Find the nearest writable cgroup root with the memory+pids controllers.

    Walks from the current process's cgroup (``/proc/self/cgroup`` v2 line)
    upward; a candidate qualifies only when a real probe (create child,
    write ``memory.max``, remove child) succeeds there. Returns
    ``(root_path_or_None, controllers, notes)``; notes carry the honest
    delegation facts for the evidence record.
    """
    notes: list[str] = []
    v2_line = next(
        (line for line in _read(Path("/proc/self/cgroup")).splitlines() if line.startswith("0::")),
        "",
    )
    if not v2_line:
        notes.append("no cgroup v2 hierarchy mounted for this process")
        return None, (), notes
    relative = v2_line[3:].lstrip("/")
    literal_check = (
        CGROUP_FS / "user.slice" / f"user-{os.getuid()}.slice" / "cgroup.subtree_control"
    )
    literal_writable = os.access(literal_check, os.W_OK) if literal_check.exists() else False
    notes.append(
        f"user.slice/user-{os.getuid()}.slice/cgroup.subtree_control writable={literal_writable}"
        " (systemd delegates at user@.service level instead)"
    )
    nodes: list[Path] = []
    current = CGROUP_FS / relative
    while True:
        nodes.append(current)
        if current == CGROUP_FS:
            break
        current = current.parent
    for node in nodes:
        controllers = tuple(_read(node / "cgroup.controllers").split())
        if not {"memory", "pids"}.issubset(controllers):
            continue
        if not (node.is_dir() and os.access(node, os.W_OK)):
            continue
        if _probe_writable(node):
            return str(node), controllers, notes
    notes.append("no writable delegated cgroup root with memory+pids controllers found")
    return None, (), notes


def _probe_writable(node: Path) -> bool:
    probe = node / f".probe-{os.getpid()}"
    try:
        probe.mkdir()
        _write(probe / "memory.max", "268435456")
    except OSError:
        return False
    try:
        probe.rmdir()
    except OSError:
        return False
    return True


class DelegatedCgroupController:
    """Owns the per-deployment execution slice below the delegated root."""

    def __init__(self, root: Path, *, slice_name: str = EXEC_SLICE_NAME) -> None:
        """Bind the delegated root and ensure the execution slice exists."""
        self._root = root
        self._slice = root / slice_name
        self._slice.mkdir(parents=True, exist_ok=True)
        for controller in ("cpu", "memory", "pids"):
            try:
                _write(self._slice / "cgroup.subtree_control", f"+{controller}")
            except OSError:
                # Controller unavailable at this level (e.g. cpu): its limit
                # is skipped; memory/pids availability is gated by discovery.
                continue

    @property
    def slice_path(self) -> str:
        """The execution slice directory (audit/evidence fact)."""
        return str(self._slice)

    @contextmanager
    def execution_cgroup(
        self, execution_id: str, limits: ExecutionLimits
    ) -> Iterator[ExecutionCgroup]:
        """Create, yield, and always clean up one per-execution subtree."""
        group = ExecutionCgroup(self._slice / f"exec-{execution_id}", limits)
        group.create()
        try:
            yield group
        finally:
            group.cleanup()


class ExecutionCgroup:
    """One per-execution cgroup subtree with limits, OOM accounting, kill."""

    def __init__(self, path: Path, limits: ExecutionLimits) -> None:
        """Bind the cgroup directory and its limits."""
        self._path = path
        self._limits = limits
        self._initial_oom = 0

    def create(self) -> None:
        """Create the subtree and apply the resource limits."""
        self._path.mkdir()
        _write(self._path / "memory.max", str(self._limits.memory_max_bytes))
        # swap.max defaults to "max" on the delegated slice: without this the
        # hard memory ceiling leaks into swap (tmpfs overflow swaps out
        # instead of OOM-killing), so the hard boundary requires swap off.
        _write(self._path / "memory.swap.max", "0")
        _write(self._path / "pids.max", str(self._limits.pids_max))
        quota = max(_QUOTA_FLOOR_MICROS, self._limits.cpu_quota_micros)
        period = max(_QUOTA_FLOOR_MICROS, self._limits.cpu_period_micros)
        # cpu controller not delegated at this level; recorded by posture
        with contextlib.suppress(OSError):
            _write(self._path / "cpu.max", f"{quota} {period}")
        self._initial_oom = self._oom_kill_count()

    def attach(self, pid: int) -> None:
        """Move a process (and, by inheritance, its future children) in."""
        _write(self._path / "cgroup.procs", str(pid))

    def join_self(self) -> None:
        """
        Move the CALLING process in — the between-fork-and-exec hook.

        Joining before ``exec`` is the race-free form: the sandboxed payload
        is forked by the joined process, so it and every descendant inherit
        the resource limits from the first instruction onward. Used as the
        ``preexec_fn`` of the sandbox launch.
        """
        _write(self._path / "cgroup.procs", str(os.getpid()))

    def kill(self) -> None:
        """Kill every process in the subtree atomically (cgroup.kill)."""
        try:
            _write(self._path / "cgroup.kill", "1")
        except OSError as exc:
            if exc.errno not in (errno.ENOENT, errno.EACCES, errno.EBUSY):
                raise

    def _oom_kill_count(self) -> int:
        for line in _read(self._path / "memory.events").splitlines():
            key, sep, value = line.partition(" ")
            if sep and key == "oom_kill":
                try:
                    return int(value)
                except ValueError:
                    return 0
        return 0

    @property
    def oom_kill_count(self) -> int:
        """OOM kills charged to this subtree during the execution."""
        return max(0, self._oom_kill_count() - self._initial_oom)

    def cleanup(self) -> None:
        """Remove the subtree (fail-tolerant: a stuck proc is reaped first)."""
        self.kill()
        with contextlib.suppress(OSError):
            self._path.rmdir()
