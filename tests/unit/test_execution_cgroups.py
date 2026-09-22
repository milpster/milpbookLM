from __future__ import annotations

from pathlib import Path

import pytest
from milpbooklm_adapters.execution import cgroups
from milpbooklm_adapters.execution.cgroups import ExecutionCgroup
from milpbooklm_application.execution import ExecutionLimits


def test_execution_cgroup_applies_limits_and_tracks_oom(tmp_path: Path) -> None:
    path = tmp_path / "exec-test"
    group = ExecutionCgroup(
        path,
        ExecutionLimits(
            memory_max_bytes=1024,
            pids_max=7,
            cpu_quota_micros=2000,
            cpu_period_micros=4000,
        ),
    )

    group.create()
    (path / "memory.events").write_text("oom_kill 2\n")
    group.attach(1234)
    group.kill()

    assert (path / "memory.max").read_text() == "1024"
    assert (path / "pids.max").read_text() == "7"
    assert (path / "cpu.max").read_text() == "2000 4000"
    assert (path / "cgroup.procs").read_text() == "1234"
    assert (path / "cgroup.kill").read_text() == "1"
    expected_oom_kills = 2
    assert group.oom_kill_count == expected_oom_kills


def test_discovery_resolves_absolute_proc_path_below_cgroup_mount(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mount = tmp_path / "cgroup"
    delegated = mount / "user.slice" / "test.scope"
    delegated.mkdir(parents=True)
    (delegated / "cgroup.controllers").write_text("cpu memory pids")
    original_read = cgroups._read
    monkeypatch.setattr(cgroups, "CGROUP_FS", mount)
    monkeypatch.setattr(
        cgroups,
        "_read",
        lambda path: (
            "0::/user.slice/test.scope"
            if path == Path("/proc/self/cgroup")
            else original_read(path)
        ),
    )
    monkeypatch.setattr(cgroups, "_probe_writable", lambda node: node == delegated)

    root, controllers, _notes = cgroups.discover_delegated_cgroup_root()

    assert root == str(delegated)
    assert controllers == ("cpu", "memory", "pids")
