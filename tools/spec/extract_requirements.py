"""
Requirement-extraction conformance checker (TECH-00-001 / TECH-00-002).

The frozen ledger ``requirements.generated.json`` assigns each normative
occurrence a stable ID, a classification and a fingerprint. The fingerprint is
defined by the generator contract as:

    SHA-256(source + LF + term + LF + occurrence_on_line + LF +
             whitespace-normalized statement)

This tool recomputes every fingerprint and re-asserts the structural invariants
of the ledger (valid IDs, valid classifications, valid specification statuses).
It is the CI gate that "fails on unclassified occurrences": a requirement that
cannot be re-derived from its source is a specification defect.

Exit codes: 0 = all invariants hold, 1 = one or more invariants failed.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

LEDGER = (
    Path(__file__).resolve().parents[2]
    / "milpbookml-implementation-guide"
    / "requirements.generated.json"
)

# ARCH-CC-NNN (architecture) and TECH-CC-NNN (technical), CC = two-digit chapter.
ID_RE = re.compile(r"^(ARCH|TECH)-\d{2}-\d{3}$")
CLASSIFICATIONS = {"must", "must_not", "should", "should_not", "narrative"}
SPEC_STATUSES = {"specified", "classified"}


@dataclass(frozen=True, slots=True)
class Violation:
    """A single ledger invariant violation."""

    req_id: str
    field: str
    detail: str


def _whitespace_normalized(statement: str) -> str:
    return " ".join(statement.split())


def _expected_fingerprint(source: str, term: str, occurrence: int, statement: str) -> str:
    payload = f"{source}\n{term}\n{occurrence}\n{_whitespace_normalized(statement)}"
    return hashlib.sha256(payload.encode()).hexdigest()


def check_ledger(ledger_path: Path) -> list[Violation]:
    """Re-derive every fingerprint + classification; return all violations."""
    data = json.loads(ledger_path.read_text())
    requirements = data["requirements"]
    violations: list[Violation] = []
    seen_ids: set[str] = set()

    for req in requirements:
        rid = req["id"]
        if not ID_RE.match(rid):
            violations.append(Violation(rid, "id", f"malformed id: {rid!r}"))
        if rid in seen_ids:
            violations.append(Violation(rid, "id", "duplicate id"))
        seen_ids.add(rid)

        if req.get("classification") not in CLASSIFICATIONS:
            violations.append(
                Violation(rid, "classification", f"unclassified: {req.get('classification')!r}")
            )
        if req.get("specification_status") not in SPEC_STATUSES:
            detail = f"bad status: {req.get('specification_status')!r}"
            violations.append(Violation(rid, "specification_status", detail))
        expected = _expected_fingerprint(
            req["source"], req["term"], req["occurrence_on_line"], req["statement"]
        )
        if expected != req["fingerprint_sha256"]:
            violations.append(Violation(rid, "fingerprint_sha256", f"expected {expected[:16]}…"))

    return violations


def main(argv: list[str]) -> int:
    """CLI entry point: check the ledger, exit 0 on conformance."""
    ledger = Path(argv[1]) if len(argv) > 1 else LEDGER
    if not ledger.exists():
        print(f"ledger not found: {ledger}", file=sys.stderr)
        return 1
    violations = check_ledger(ledger)
    if violations:
        for v in violations:
            print(f"FAIL {v.req_id} [{v.field}] {v.detail}", file=sys.stderr)
        print(f"{len(violations)} ledger violation(s)", file=sys.stderr)
        return 1
    print("ledger conformance OK (all fingerprints + classifications re-derived)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
