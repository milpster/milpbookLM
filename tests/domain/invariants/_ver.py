"""VER evidence writer for the FND-03 domain invariants.

Local to this task (tests/_evidence.py belongs to FND-01 and stays untouched): each
ver-* test calls write_ver as its LAST statement, so a record is only persisted when
every assertion in the test has already passed.
"""

from __future__ import annotations

import json
import platform
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = REPO_ROOT / "artifacts" / "verification"


def write_ver(
    *,
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
        "task": "FND-03",
        "test_path": test_path,
        "result": "passed",
        "timestamp": datetime.now(UTC).isoformat(),
        "checks": checks,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "host": platform.node(),
            "postgres": "18.6 (digest-pinned pgvector/pgvector:pg18, direct binary run)",
        },
    }
    path = EVIDENCE_DIR / f"{verification_id}.json"
    path.write_text(json.dumps(record, indent=2) + "\n")
    return path
