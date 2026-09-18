"""VER-ARCH-02-003 (ARCH-02-003): exports are portable snapshots, never Google-coupled.

Oracle: the prohibited behavior (claiming Google-account coupling or ACL
propagation into independently distributed copies) is specifically attempted
and remains absent/denied. Google coupling is a deliberate non-target;
exported files are detached snapshots per the frozen parity matrix.
"""

from __future__ import annotations

import json

from tests._evidence import REPO_ROOT
from tests.meta._evidence_fnd02 import write_evidence_fnd02
from tests.meta._tools import load_tool

CONFORMANCE = REPO_ROOT / "artifacts" / "conformance.json"


def _caps() -> dict[str, dict]:
    return {
        cap["id"]: cap for cap in load_tool("check_capabilities").load_registry()["capabilities"]
    }


def test_google_account_coupling_is_deliberate_non_target() -> None:
    cap = _caps()["google_account_coupling"]
    assert cap["classification"] == "deliberate-non-target"
    assert cap["implemented"] is False
    assert cap["enabled"] is False
    assert cap["phase"] is None
    assert cap["feature_flag"] is None


def test_export_contract_is_detached_snapshot_not_acl_propagation() -> None:
    cap = _caps()["artifact_lifecycle"]
    text = cap["reference_text"].lower()
    assert "detached snapshots" in text, "export contract lost the detached-snapshot semantics"
    assert "cannot revoke an independent external copy" in text, (
        "export contract must state no ACL propagation into distributed copies"
    )


def test_google_coupling_not_advertised() -> None:
    doc = json.loads(CONFORMANCE.read_text(encoding="utf-8"))
    assert "google_account_coupling" not in set(doc["advertised"])
    entry = next(cap for cap in doc["capabilities"] if cap["id"] == "google_account_coupling")
    assert entry["effective"] is False


def test_evidence_record_written() -> None:
    write_evidence_fnd02(
        "VER-ARCH-02-003",
        "ARCH-02-003",
        "tests/meta/capabilities/ver-arch-02-003.py",
        {
            "google_account_coupling": "deliberate-non-target, inert, unadvertised",
            "export_contract": "detached snapshots; no ACL propagation claim",
        },
    )
    evidence = REPO_ROOT / "artifacts" / "verification" / "VER-ARCH-02-003.json"
    assert evidence.exists()
