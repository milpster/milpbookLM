"""
Host prerequisite probe for the local-bubblewrap provider (EXE-01, arch ch12 §11).

Installation/health checks MUST reject a setuid-marked ``bwrap`` binary and
MUST verify the required namespace operations before enabling model-driven
execution. This probe is the fail-closed source of those facts: every check
runs for real (version parse, namespace smoke launch, seccomp capability
probe, cgroup v2 delegation discovery) and an unsatisfied mandatory check
reports the capability unavailable - it never weakens isolation.

Recorded honest deltas on the reference host (see task-29 evidence): bwrap
0.11.0 predates the 0.12.0 GHSA-pxhw-h44j-8pfx sandbox-setup symlink-traversal
fix; the broker's launcher mitigates by constructing the entire bwrap argv
itself from broker-generated, symlink-free mount sources (no client path ever
reaches bwrap). The kernel CAN install seccomp filters through bwrap
(verified: ``Seccomp: 2`` with one filter), but no reviewed filter is
curated for the prototype runtime image, so the SHOULD-level seccomp policy
is deferred (omitted honestly, never faked). An earlier host fact recorded
seccomp as EINVAL-unsupported; that measurement did not hold under the real
sandbox launch path and is corrected here.
"""

from __future__ import annotations

import os
import re
import stat
import struct
import subprocess
from pathlib import Path
from typing import Final

from milpbooklm_application.execution import ExecutionHostPosture

from milpbooklm_adapters.execution.cgroups import discover_delegated_cgroup_root

_MIN_BWRAP_SMOKE_TIMEOUT: Final = 10.0
_SECCOMP_RET_ALLOW: Final = 0x7FFF0000
_BPF_RET_K: Final = 0x06
_SECCOMP_FILTER: Final = struct.pack("HBBI", _BPF_RET_K, 0, 0, _SECCOMP_RET_ALLOW)


def probe_execution_host(bwrap_path: str | Path = "/usr/bin/bwrap") -> ExecutionHostPosture:
    """
    Verify every mandatory prerequisite for real and return the posture.

    The userns smoke uses the same namespace set the sandbox uses (without
    seccomp, which is probed separately so a missing filter cannot mask a
    namespace failure).
    """
    path = Path(bwrap_path)
    notes: list[str] = []
    version: str | None = None
    setuid = False
    userns = False
    seccomp = False

    try:
        mode = stat.S_IMODE(path.stat().st_mode)
        setuid = bool(mode & stat.S_ISUID)
    except OSError as exc:
        notes.append(f"bwrap binary unreadable: {exc.__class__.__name__}")
        return ExecutionHostPosture(
            bwrap_path=str(path),
            bwrap_version=None,
            bwrap_setuid=setuid,
            userns_supported=False,
            seccomp_supported=False,
            kernel_release=os.uname().release,
            cgroup_root=None,
            cgroup_controllers=(),
            notes=tuple(notes),
        )

    version = _bwrap_version(path)
    if version is None:
        notes.append("bwrap --version did not parse")
    elif _version_tuple(version) < (0, 11, 0):
        notes.append(f"bwrap {version} is older than the reviewed 0.11 baseline")
    elif _version_tuple(version) < (0, 12, 0):
        notes.append(
            "bwrap "
            + version
            + " predates 0.12.0 (GHSA-pxhw-h44j-8pfx sandbox-setup symlink traversal;"
            " broker-only argv + symlink-free mount sources mitigate; admin upgrade pending)"
        )

    if setuid:
        notes.append("bwrap binary is setuid-marked: rejected (arch ch12 §11)")

    if version is not None and not setuid:
        userns = _userns_smoke(path)
        if not userns:
            notes.append("user namespace smoke launch failed: unprivileged userns unavailable")
        seccomp = _seccomp_smoke(path)
        if not seccomp:
            notes.append(
                "seccomp filter unsupported on this kernel: policy omitted (recorded, not faked)"
            )

    cgroup_root, controllers, cgroup_notes = discover_delegated_cgroup_root()
    notes.extend(cgroup_notes)

    return ExecutionHostPosture(
        bwrap_path=str(path),
        bwrap_version=version,
        bwrap_setuid=setuid,
        userns_supported=userns,
        seccomp_supported=seccomp,
        kernel_release=os.uname().release,
        cgroup_root=cgroup_root,
        cgroup_controllers=controllers,
        notes=tuple(notes),
    )


def _bwrap_version(path: Path) -> str | None:
    try:
        completed = subprocess.run(  # noqa: S603 - administrator-selected absolute binary
            [str(path), "--version"],
            capture_output=True,
            text=True,
            timeout=_MIN_BWRAP_SMOKE_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"(\d+\.\d+\.\d+)", completed.stdout)
    return match.group(1) if match else None


def _userns_smoke(path: Path) -> bool:
    try:
        completed = subprocess.run(  # noqa: S603 - probed absolute binary, fixed policy argv
            [
                str(path),
                "--unshare-user",
                "--unshare-pid",
                "--unshare-ipc",
                "--unshare-uts",
                "--unshare-net",
                "--unshare-cgroup",
                "--disable-userns",
                "--assert-userns-disabled",
                "--ro-bind",
                "/usr",
                "/usr",
                "--symlink",
                "usr/bin",
                "/bin",
                "--symlink",
                "usr/lib",
                "/lib",
                "--symlink",
                "usr/lib64",
                "/lib64",
                "--dev",
                "/dev",
                "--proc",
                "/proc",
                "--cap-drop",
                "ALL",
                "/usr/bin/busybox",
                "true",
            ],
            capture_output=True,
            timeout=_MIN_BWRAP_SMOKE_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def _seccomp_smoke(path: Path) -> bool:
    try:
        read_fd, write_fd = os.pipe()
        os.write(write_fd, _SECCOMP_FILTER)
        os.close(write_fd)
        try:
            completed = subprocess.run(  # noqa: S603 - probed absolute binary, fixed policy argv
                [
                    str(path),
                    "--unshare-user",
                    "--ro-bind",
                    "/usr",
                    "/usr",
                    "--symlink",
                    "usr/bin",
                    "/bin",
                    "--seccomp",
                    str(read_fd),
                    "/usr/bin/busybox",
                    "true",
                ],
                capture_output=True,
                timeout=_MIN_BWRAP_SMOKE_TIMEOUT,
                check=False,
                pass_fds=(read_fd,),
            )
        finally:
            os.close(read_fd)
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def _version_tuple(version: str) -> tuple[int, int, int]:
    major, minor, patch = version.split(".")
    return int(major), int(minor), int(patch)
