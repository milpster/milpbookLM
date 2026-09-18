"""Evidence writer for FND-02 VER-mapped tests (task FND-02)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from tests._evidence import EVIDENCE_DIR, environment


def write_evidence_fnd02(
    verification_id: str,
    requirement_id: str,
    test_path: str,
    checks: dict[str, object],
) -> Path:
    """Persist a passed-verification record stamped with task FND-02."""
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "verification_id": verification_id,
        "requirement_id": requirement_id,
        "task": "FND-02",
        "test_path": test_path,
        "result": "passed",
        "timestamp": datetime.now(UTC).isoformat(),
        "checks": checks,
        "environment": environment(),
    }
    path = EVIDENCE_DIR / f"{verification_id}.json"
    path.write_text(json.dumps(record, indent=2) + "\n")
    return path
