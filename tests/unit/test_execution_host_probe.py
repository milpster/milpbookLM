from __future__ import annotations

from pathlib import Path

import pytest
from milpbooklm_adapters.execution.host_probe import probe_execution_host
from milpbooklm_application.execution import ExecutionHostPosture


def _fake_bwrap(path: Path, version: str) -> Path:
    path.write_text(
        f'#!/bin/sh\nif [ "$1" = "--version" ]; then echo \'bubblewrap {version}\'; fi\nexit 0\n'
    )
    path.chmod(0o700)
    return path


def test_host_probe_uses_real_fake_binary_path_and_all_mandatory_controllers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cgroup_root = tmp_path / "cgroup"
    cgroup_root.mkdir()
    monkeypatch.setattr(
        "milpbooklm_adapters.execution.host_probe.discover_delegated_cgroup_root",
        lambda: (str(cgroup_root), ("cpu", "memory", "pids"), []),
    )

    posture = probe_execution_host(_fake_bwrap(tmp_path / "bwrap", "0.11.0"))

    assert posture.execution_available
    assert posture.userns_supported
    assert posture.seccomp_supported
    assert posture.cgroup_root == str(cgroup_root)


def test_host_probe_rejects_setuid_binary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    binary = _fake_bwrap(tmp_path / "bwrap", "0.12.0")
    binary.chmod(0o4700)
    monkeypatch.setattr(
        "milpbooklm_adapters.execution.host_probe.discover_delegated_cgroup_root",
        lambda: (str(tmp_path), ("cpu", "memory", "pids"), []),
    )

    posture = probe_execution_host(binary)

    assert posture.bwrap_setuid
    assert not posture.execution_available


def test_cpu_controller_is_mandatory_for_execution_availability() -> None:
    posture = ExecutionHostPosture(
        bwrap_path="/usr/bin/bwrap",
        bwrap_version="0.12.0",
        bwrap_setuid=False,
        userns_supported=True,
        seccomp_supported=False,
        kernel_release="test",
        cgroup_root="/sys/fs/cgroup/test",
        cgroup_controllers=("memory", "pids"),
    )

    assert not posture.execution_available


def test_old_version_is_compared_numerically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "milpbooklm_adapters.execution.host_probe.discover_delegated_cgroup_root",
        lambda: (str(tmp_path), ("cpu", "memory", "pids"), []),
    )

    posture = probe_execution_host(_fake_bwrap(tmp_path / "bwrap", "0.9.0"))

    assert any("older than" in note for note in posture.notes)
