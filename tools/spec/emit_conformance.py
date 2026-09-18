"""
Emit artifacts/conformance.json for the current build (TECH-00-003).

Reads the frozen capability registry (capabilities.generated.json) and the
requirement ledger, then writes the per-build conformance profile:
capability ID, architecture classification, implementation status, enabled
state, dependencies and test lists. Skeleton state: nothing is enabled and
nothing is advertised (disabled optionals must stay visible, never advertised).
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GUIDE = REPO_ROOT / "milpbookml-implementation-guide"
CAPABILITIES = GUIDE / "capabilities.generated.json"
LEDGER = GUIDE / "requirements.generated.json"
OUT = REPO_ROOT / "artifacts" / "conformance.json"


def _git_sha() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO_ROOT, check=False
    )
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def emit() -> Path:
    """Write artifacts/conformance.json for the current build; return its path."""
    capabilities = json.loads(CAPABILITIES.read_text())["capabilities"]
    ledger = json.loads(LEDGER.read_text())["requirements"]
    doc = {
        "schema_version": 1,
        "generated_by": "tools/spec/emit_conformance.py",
        "task": "FND-01",
        "build": _git_sha(),
        "timestamp": datetime.now(UTC).isoformat(),
        "requirements_total": len(ledger),
        "capabilities": [
            {
                "id": cap["id"],
                "classification": cap["classification"],
                "implementation_status": cap["implementation_status"],
                "enabled": cap["implemented"] and cap["enabled"],
                "dependencies": cap["dependencies"],
                "automated_tests": cap["automated_tests"],
                "manual_tests": cap["manual_tests"],
            }
            for cap in capabilities
        ],
        # Nothing is advertised by the skeleton: stable/core is not implemented,
        # and optional features must remain visible as disabled, never advertised.
        "advertised": [],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2) + "\n")
    return OUT


if __name__ == "__main__":
    print(f"wrote {emit()}")
