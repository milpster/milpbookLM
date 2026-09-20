"""
Emit artifacts/conformance.json for the current build (TECH-00-003, ch00).

Reads the packaged reviewed capability registry (milpbooklm_contracts/capabilities.yaml)
and the requirement ledger, computes effective capability state via the
feature-gating skeleton, and writes the per-build conformance profile:
capability ID, architecture classification, implementation status, enabled
state, effective state, dependencies and test lists. Disabled optional
features remain visible as disabled and are never advertised; stable/core
capabilities are never not_applicable.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

# When run as `python tools/spec/emit_conformance.py` the script directory is
# sys.path[0], so the sibling tools import directly.
from check_capabilities import load_registry
from effective_state import CapabilityPolicy, compute_effective_states

REPO_ROOT = Path(__file__).resolve().parents[2]
GUIDE = REPO_ROOT / "milpbookml-implementation-guide"
LEDGER = GUIDE / "requirements.generated.json"
OUT = REPO_ROOT / "artifacts" / "conformance.json"


def _git_sha() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO_ROOT, check=False
    )
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def emit() -> Path:
    """Write artifacts/conformance.json for the current build; return its path."""
    registry = load_registry(
        REPO_ROOT / "packages" / "contracts" / "src" / "milpbooklm_contracts" / "capabilities.yaml"
    )
    capabilities = registry["capabilities"]
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))["requirements"]
    # Feature gating (ch02): compiled support + administrator policy +
    # configured providers + dependency health. The skeleton ships no
    # providers and no dependency health reports, so every capability is
    # effectively disabled by default — including optional/provisional.
    states = compute_effective_states(capabilities, policy=CapabilityPolicy(), dependency_health={})
    doc = {
        "schema_version": 1,
        "generated_by": "tools/spec/emit_conformance.py",
        "task": "FND-02",
        "build": _git_sha(),
        "timestamp": datetime.now(UTC).isoformat(),
        "requirements_total": len(ledger),
        "capabilities": [
            {
                "id": cap["id"],
                "classification": cap["classification"],
                "implementation_status": cap["implementation_status"],
                "enabled": cap["implemented"] and cap["enabled"],
                "effective": states[str(cap["id"])].enabled,
                "effective_reason": states[str(cap["id"])].reason,
                "dependencies": cap["dependencies"],
                "automated_tests": cap["automated_tests"],
                "manual_tests": cap["manual_tests"],
            }
            for cap in capabilities
        ],
        # Nothing is advertised while nothing is effective: stable/core is
        # not implemented, and disabled optionals must stay visible,
        # never advertised.
        "advertised": [],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2) + "\n")
    return OUT


if __name__ == "__main__":
    print(f"wrote {emit()}")
