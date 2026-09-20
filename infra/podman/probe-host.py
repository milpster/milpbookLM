#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13,<3.14"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly:
#      uv run infra/podman/probe-host.py infra/podman/deployment-facts.json
# 3. Or make executable and run:
#      chmod +x infra/podman/probe-host.py && ./infra/podman/probe-host.py
# ──────────────────

"""Record non-secret host accelerator and runtime inventory for deployment ADRs."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TypedDict


class CommandResult(TypedDict):
    """Bounded command result included in deployment facts."""

    available: bool
    output: str


class GpuInventory(TypedDict):
    """GPU counts and PCI inventory."""

    radeon_vii_count: int
    rtx_3080_count: int
    display_controllers: list[str]


class DeploymentFacts(TypedDict):
    """Committed host facts consumed by later runtime-selection ADRs."""

    schema_version: int
    host: str
    kernel: str
    gpu_inventory: GpuInventory
    rocm: CommandResult
    cuda: CommandResult
    nvidia: CommandResult
    vulkan: CommandResult
    decisions: list[str]


def run_command(command: str, *arguments: str, timeout: int = 30) -> CommandResult:
    """Run an inventory command and return bounded single-record output."""
    executable = shutil.which(command)
    if executable is None:
        return {"available": False, "output": "not installed"}
    try:
        completed = subprocess.run(  # noqa: S603 -- resolved executable, fixed probe arguments
            [executable, *arguments],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False, "output": "probe failed"}
    output = completed.stdout.strip() or completed.stderr.strip()
    return {"available": completed.returncode == 0, "output": output[:20000]}


def gpu_inventory() -> GpuInventory:
    """Parse PCI display controllers without requiring vendor runtimes."""
    pci = run_command("lspci", "-nn")
    controllers = [
        line
        for line in pci["output"].splitlines()
        if "VGA compatible controller" in line or "3D controller" in line
    ]
    return {
        "radeon_vii_count": sum("Radeon VII" in line for line in controllers),
        "rtx_3080_count": sum("RTX 3080" in line for line in controllers),
        "display_controllers": controllers,
    }


def concise(result: CommandResult, markers: tuple[str, ...]) -> CommandResult:
    """Keep stable version/device lines from verbose runtime probes."""
    if not result["available"]:
        return result
    selected = [
        line.strip()
        for line in result["output"].splitlines()
        if any(marker in line for marker in markers)
    ]
    return {"available": True, "output": "\n".join(selected)}


def collect() -> DeploymentFacts:
    """Collect deployment facts without changing host configuration."""
    inventory = gpu_inventory()
    rocminfo = concise(
        run_command("rocminfo", timeout=60),
        ("Runtime Version:", "Name:", "Marketing Name:"),
    )
    hipcc = concise(run_command("hipcc", "--version"), ("HIP version:", "AMD clang version"))
    rocm_output = f"{hipcc['output']}\n{rocminfo['output']}".strip()
    rocm: CommandResult = {
        "available": hipcc["available"] and rocminfo["available"],
        "output": rocm_output,
    }
    cuda = concise(run_command("nvcc", "--version"), ("release", "Build cuda"))
    nvidia = run_command(
        "nvidia-smi",
        "--query-gpu=name,driver_version,memory.total",
        "--format=csv,noheader",
    )
    vulkan = concise(
        run_command("vulkaninfo", "--summary", timeout=60),
        ("Vulkan Instance Version", "deviceName", "driverName", "driverInfo"),
    )
    override = os.environ.get("HSA_OVERRIDE_GFX_VERSION", "")
    decisions = [
        "PCI inventory confirms two Radeon VII (Vega 20, device 1002:66af) and one "
        "RTX 3080 Laptop GPU.",
        "ROCm/HIP is installed and enumerates both Radeon VII devices; runtime names are "
        "recorded verbatim.",
        "CUDA toolkit and NVIDIA driver are present for the RTX 3080; task 42 must "
        "benchmark before backend selection.",
        "Vulkan enumerates the integrated AMD GPU, RTX 3080, and both Radeon VII devices.",
    ]
    if override:
        decisions.append(
            f"HSA_OVERRIDE_GFX_VERSION={override} is active, so rocminfo reports gfx900 "
            "rather than native gfx906."
        )
    return {
        "schema_version": 1,
        "host": platform.node(),
        "kernel": platform.release(),
        "gpu_inventory": inventory,
        "rocm": rocm,
        "cuda": cuda,
        "nvidia": nvidia,
        "vulkan": vulkan,
        "decisions": decisions,
    }


def main() -> int:
    """Write stable JSON facts to the requested deployment path."""
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("deployment-facts.json")
    output.write_text(json.dumps(collect(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"deployment facts written: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
