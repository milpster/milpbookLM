"""Shared evidence writer for VER-mapped verification tests (FND-01)."""

from __future__ import annotations

import json
import platform
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = REPO_ROOT / "artifacts" / "verification"


def environment() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "host": platform.node(),
    }


def write_evidence(
    verification_id: str,
    requirement_id: str,
    test_path: str,
    checks: dict[str, object],
) -> Path:
    """Persist a passed-verification record to artifacts/verification/."""
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "verification_id": verification_id,
        "requirement_id": requirement_id,
        "task": "FND-01",
        "test_path": test_path,
        "result": "passed",
        "timestamp": datetime.now(UTC).isoformat(),
        "checks": checks,
        "environment": environment(),
    }
    path = EVIDENCE_DIR / f"{verification_id}.json"
    path.write_text(json.dumps(record, indent=2) + "\n")
    return path
