"""
Requirement-extraction conformance checker (TECH-00-001 / TECH-00-002, ch25).

The frozen ledger ``requirements.generated.json`` assigns each normative
occurrence a stable ID, a classification and a fingerprint. The fingerprint is
defined by the generator contract as:

    SHA-256(source + LF + term + LF + occurrence_on_line + LF +
             whitespace-normalized statement)

This tool:
1. re-derives every ledger fingerprint and re-asserts the structural
   invariants (valid IDs, valid classifications, valid statuses);
2. validates the ledger against ``schemas/requirements-ledger.schema.json``;
3. rescans the numbered chapters (00-25 of the technical guide and of the
   architecture baseline) case-insensitively for MUST/SHOULD terms and
   matches every occurrence against the ledger's fingerprints/anchors.

It fails on added (unmapped), removed, renumbered, duplicated occurrences.
Narrative occurrences (ARCH-00-001..012) are explicitly classified, never
dropped from the census.

Exit codes: 0 = all invariants hold, 1 = one or more failed, 2 = usage.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[2]
GUIDE = REPO_ROOT / "milpbookml-implementation-guide"
LEDGER = GUIDE / "requirements.generated.json"
LEDGER_SCHEMA = GUIDE / "schemas" / "requirements-ledger.schema.json"

# ARCH-CC-NNN (architecture) and TECH-CC-NNN (technical), CC = two-digit chapter.
ID_RE = re.compile(r"^(ARCH|TECH)-\d{2}-\d{3}$")
CLASSIFICATIONS = {"must", "must_not", "should", "should_not", "narrative"}
SPEC_STATUSES = {"specified", "classified"}

# Longest term first so "MUST NOT" / "SHOULD NOT" are not double-counted as
# bare MUST/SHOULD. Word-boundary, case-insensitive (ch00: case-insensitive
# MUST/SHOULD scan of the numbered chapters).
TERM_RE = re.compile(r"\bMUST NOT\b|\bMUST\b|\bSHOULD NOT\b|\bSHOULD\b", re.IGNORECASE)

# The 12 narrative records: classified, never dropped from the census.
NARRATIVE_IDS = frozenset(f"ARCH-00-{n:03d}" for n in range(1, 13))


@dataclass(frozen=True, slots=True)
class Violation:
    """A single ledger invariant violation."""

    req_id: str
    field: str
    detail: str


@dataclass(frozen=True, slots=True)
class Occurrence:
    """One rescanned normative occurrence (source, anchor, term, fingerprint)."""

    source: str
    line: int
    occurrence_on_line: int
    term: str
    statement: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class CensusFinding:
    """A single census finding: added/removed/renumbered/duplicated/narrative."""

    kind: str
    subject: str
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


def check_schemas(guide_dir: Path = GUIDE) -> list[CensusFinding]:
    """Validate the ledger against schemas/requirements-ledger.schema.json (ch25)."""
    ledger = json.loads((guide_dir / "requirements.generated.json").read_text(encoding="utf-8"))
    schema = json.loads((guide_dir / "schemas" / "requirements-ledger.schema.json").read_text())
    validator = Draft202012Validator(schema)
    findings: list[CensusFinding] = []
    for error in sorted(validator.iter_errors(ledger), key=lambda e: list(e.path)):
        location = "/".join(str(part) for part in error.path)
        findings.append(
            CensusFinding("schema", location, f"ledger schema violation: {error.message}")
        )
    return findings


def rescan_chapters(guide_dir: Path = GUIDE) -> list[Occurrence]:
    """
    Case-insensitive MUST/SHOULD census over the numbered chapters (00-25).

    Covers the technical guide and the architecture baseline chapter sets;
    multiple occurrences on one line are counted individually.
    """
    occurrences: list[Occurrence] = []
    chapter_files = sorted(guide_dir.glob("[0-2][0-9]-*.md")) + sorted(
        (guide_dir / "architecture-baseline").glob("[0-2][0-9]-*.md")
    )
    for path in chapter_files:
        source = path.relative_to(guide_dir).as_posix()
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for occ_no, match in enumerate(TERM_RE.finditer(line), start=1):
                term = match.group(0).upper()
                occurrences.append(
                    Occurrence(
                        source=source,
                        line=line_no,
                        occurrence_on_line=occ_no,
                        term=term,
                        statement=line,
                        fingerprint=_expected_fingerprint(source, term, occ_no, line),
                    )
                )
    return occurrences


def _ledger_fingerprint_index(
    requirements: list[dict],
) -> tuple[dict[str, str], list[CensusFinding]]:
    """Map fingerprint -> first ledger id; report duplicates."""
    seen: dict[str, str] = {}
    findings: list[CensusFinding] = []
    for req in requirements:
        fingerprint = req["fingerprint_sha256"]
        if fingerprint in seen:
            findings.append(
                CensusFinding(
                    "duplicated",
                    req["id"],
                    f"fingerprint {fingerprint[:16]}… shared with {seen[fingerprint]}",
                )
            )
        else:
            seen[fingerprint] = req["id"]
    return seen, findings


def _guide_occurrence_index(
    occurrences: list[Occurrence],
) -> tuple[dict[str, Occurrence], list[CensusFinding]]:
    """Map fingerprint -> first guide occurrence; report duplicates."""
    by_fp: dict[str, Occurrence] = {}
    findings: list[CensusFinding] = []
    for occ in occurrences:
        if occ.fingerprint in by_fp:
            findings.append(
                CensusFinding(
                    "duplicated",
                    f"{occ.source}:{occ.line}",
                    f"identical occurrence repeated (fingerprint {occ.fingerprint[:16]}…)",
                )
            )
        else:
            by_fp[occ.fingerprint] = occ
    return by_fp, findings


def _match_ledger_to_guide(
    requirements: list[dict], occurrence_by_fp: dict[str, Occurrence]
) -> tuple[list[CensusFinding], int]:
    """Classify each ledger entry as removed, renumbered, or matched."""
    findings: list[CensusFinding] = []
    matched = 0
    for req in requirements:
        occ = occurrence_by_fp.get(req["fingerprint_sha256"])
        if occ is None:
            findings.append(
                CensusFinding(
                    "removed",
                    req["id"],
                    f"ledger entry has no occurrence in {req['source']} (was it deleted?)",
                )
            )
        elif (occ.line, occ.occurrence_on_line) != (req["line"], req["occurrence_on_line"]):
            findings.append(
                CensusFinding(
                    "renumbered",
                    req["id"],
                    f"anchor moved: ledger {req['source']}:{req['line']} occ "
                    f"{req['occurrence_on_line']} -> guide {occ.line} occ {occ.occurrence_on_line}",
                )
            )
        else:
            matched += 1
    return findings, matched


def _unmapped_occurrences(
    occurrence_by_fp: dict[str, Occurrence], ledger_fingerprints: set[str]
) -> list[CensusFinding]:
    """Guide occurrences with no ledger entry (added requirements)."""
    findings: list[CensusFinding] = []
    for fingerprint, occ in occurrence_by_fp.items():
        if fingerprint not in ledger_fingerprints:
            findings.append(
                CensusFinding(
                    "added",
                    f"{occ.source}:{occ.line} occ {occ.occurrence_on_line} [{occ.term}]",
                    f"unmapped occurrence, no ledger entry: "
                    f'"{_whitespace_normalized(occ.statement)[:120]}"',
                )
            )
    return findings


def _narrative_drift(requirements: list[dict]) -> list[CensusFinding]:
    """Check the 12 narrative records for existence and classification."""
    by_id = {req["id"]: req for req in requirements}
    findings: list[CensusFinding] = []
    for narrative_id in sorted(NARRATIVE_IDS):
        req = by_id.get(narrative_id)
        if req is None:
            findings.append(CensusFinding("narrative", narrative_id, "narrative record missing"))
        elif req.get("classification") != "narrative":
            findings.append(
                CensusFinding(
                    "narrative",
                    narrative_id,
                    f"narrative record classified {req.get('classification')!r}, not 'narrative'",
                )
            )
    return findings


def check_occurrence_census(
    guide_dir: Path = GUIDE, ledger_path: Path = LEDGER
) -> tuple[list[CensusFinding], int]:
    """
    Match the rescan against the ledger fingerprints/anchors.

    Returns (findings, matched_count). Kinds: added (guide occurrence with no
    ledger mapping — unmapped), removed (ledger entry with no guide
    occurrence), renumbered (fingerprint present at a moved anchor),
    duplicated (fingerprint/ID appearing twice), narrative (classification
    drift on the 12 narrative records).
    """
    requirements = json.loads(ledger_path.read_text(encoding="utf-8"))["requirements"]
    findings: list[CensusFinding] = []
    ledger_fps, dup_ledger = _ledger_fingerprint_index(requirements)
    findings.extend(dup_ledger)

    occ_by_fp, dup_guide = _guide_occurrence_index(rescan_chapters(guide_dir))
    findings.extend(dup_guide)

    match_findings, matched = _match_ledger_to_guide(requirements, occ_by_fp)
    findings.extend(match_findings)

    findings.extend(_unmapped_occurrences(occ_by_fp, set(ledger_fps)))
    findings.extend(_narrative_drift(requirements))
    return findings, matched


def check_all(guide_dir: Path = GUIDE, ledger_path: Path = LEDGER) -> tuple[list[str], int]:
    """Run every gate; return (report_lines, total_findings)."""
    lines: list[str] = []
    total = 0

    violations = check_ledger(ledger_path)
    lines.extend(f"FAIL {v.req_id} [{v.field}] {v.detail}" for v in violations)
    total += len(violations)

    schema_findings = check_schemas(guide_dir)
    lines.extend(f"FAIL schema: {f.subject} — {f.detail}" for f in schema_findings)
    total += len(schema_findings)

    census_findings, matched = check_occurrence_census(guide_dir, ledger_path)
    lines.extend(f"FAIL census {f.kind}: {f.subject} — {f.detail}" for f in census_findings)
    total += len(census_findings)

    if total == 0:
        requirements = json.loads(ledger_path.read_text(encoding="utf-8"))["requirements"]
        narrative = sum(1 for req in requirements if req["classification"] == "narrative")
        lines.append(
            f"spec census OK: {len(requirements)} ledger entries, {matched} occurrences mapped "
            f"({narrative} narrative classified), ledger schema valid"
        )
    return lines, total


def _parse_cli_args(args: list[str]) -> tuple[Path, Path, bool] | None:
    """Return (guide, ledger, full_check); None after printing a usage error."""
    guide = GUIDE
    ledger = LEDGER
    full_check = False
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--check":
            full_check = True
        elif arg in ("--guide", "--ledger") and i + 1 < len(args):
            value = Path(args[i + 1])
            if arg == "--guide":
                guide = value
            else:
                ledger = value
            i += 1
        elif not arg.startswith("--"):
            ledger = Path(arg)
        else:
            print(f"unknown argument: {arg}", file=sys.stderr)
            print(
                "usage: extract_requirements.py [--check] [--guide PATH] [--ledger PATH]",
                file=sys.stderr,
            )
            return None
        i += 1
    return guide, ledger, full_check


def main(argv: list[str]) -> int:
    """
    CLI entry point.

    ``--check`` runs the full gate (structure + schema + occurrence census).
    Without it, only the ledger structural check runs (legacy behavior).
    Optional: ``--guide PATH``, ``--ledger PATH``.
    """
    parsed = _parse_cli_args(argv[1:])
    if parsed is None:
        return 2
    guide, ledger, full_check = parsed

    if not ledger.exists():
        print(f"ledger not found: {ledger}", file=sys.stderr)
        return 1

    if not full_check:
        violations = check_ledger(ledger)
        for violation in violations:
            print(
                f"FAIL {violation.req_id} [{violation.field}] {violation.detail}", file=sys.stderr
            )
        if violations:
            print(f"{len(violations)} ledger violation(s)", file=sys.stderr)
            return 1
        print("ledger conformance OK (all fingerprints + classifications re-derived)")
        return 0

    lines, total = check_all(guide, ledger)
    for line in lines:
        stream = sys.stderr if line.startswith("FAIL") else sys.stdout
        print(line, file=stream)
    if total:
        print(f"{total} finding(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
