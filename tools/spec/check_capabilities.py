"""
Capability registry gate (ch02 feature parity, TECH-02-001, ARCH-02-001..007).

The checked-in registry ``packages/contracts/capabilities.yaml`` is a reviewed
seed of ``capabilities.generated.json``. This tool reparses the frozen
architecture Chapter 02 table (parity matrix + source families) and fails if:

* a matrix row or source family is absent from the registry,
* a row/family is duplicated,
* a registry entry has no frozen-table origin (beyond the four deliberate
  non-targets),
* a row's classification does not follow its baseline priority,
* the YAML registry no longer equals the reviewed JSON seed,
* the registry fails ``schemas/capabilities.schema.json``.

The registry is never overwritten from the JSON by this tool.

Exit codes: 0 = registry conforms, 1 = one or more findings.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[2]
GUIDE = REPO_ROOT / "milpbookml-implementation-guide"
REGISTRY_YAML = REPO_ROOT / "packages" / "contracts" / "capabilities.yaml"
SEED_JSON = GUIDE / "capabilities.generated.json"
CAPABILITIES_SCHEMA = GUIDE / "schemas" / "capabilities.schema.json"
BASELINE_CH02 = GUIDE / "architecture-baseline" / "02-feature-parity-target.md"

# The four deliberate non-targets have no parity-matrix row; they originate
# from frozen ch02 prose (native mobile / PWA, Google coupling, marketplace).
NON_TARGET_IDS = frozenset(
    {
        "native_mobile_client",
        "pwa_offline_client",
        "google_account_coupling",
        "third_party_plugin_marketplace",
    }
)

# The frozen ch02 parity table has exactly three cells: Area | Target | Priority.
MATRIX_COLUMNS = 3

# Frozen ch02 "Baseline priority" cell -> registry classification (normalized).
PRIORITY_TO_CLASSIFICATION: dict[str, str] = {
    "core": "stable/core",
    "coreearly": "stable/core",
    "parity": "stable/core",
    "lowcostuiparity": "stable/core",
    "coreclientarchitecture": "stable/core",
    "coreprojectrequirement": "stable/core",
    "provisionalannounced": "provisional/announced",
    "advancedparity": "advanced/provider-dependent",
    "lateoptionalparity": "late/optional",
    "deferredconnectorhook": "late/optional",
}


@dataclass(frozen=True, slots=True)
class Problem:
    """A single registry conformance finding."""

    kind: str
    subject: str
    detail: str


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def load_registry(path: Path = REGISTRY_YAML) -> dict:
    """Parse the checked-in YAML registry into its full document form."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or "capabilities" not in doc:
        raise ValueError(f"registry has no 'capabilities' list: {path}")
    return doc


def validate_registry_schema(doc: dict, schema_path: Path = CAPABILITIES_SCHEMA) -> list[Problem]:
    """Validate the registry document against schemas/capabilities.schema.json."""
    validator = Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8")))
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
    return [
        Problem(
            "schema",
            "/".join(str(p) for p in error.path),
            f"schema violation: {error.message}",
        )
        for error in errors
    ]


@dataclass(frozen=True, slots=True)
class MatrixRow:
    """One frozen Chapter 02 parity-matrix row."""

    area: str
    target_capability: str
    baseline_priority: str


def parse_frozen_chapter(path: Path = BASELINE_CH02) -> tuple[list[MatrixRow], list[str]]:
    """Reparse the frozen ch02 parity matrix and source-family bullets."""
    lines = path.read_text(encoding="utf-8").splitlines()
    matrix_start = next(i for i, line in enumerate(lines) if line.startswith("## 2."))
    families_start = next(i for i, line in enumerate(lines) if line.startswith("## 3."))
    rows: list[MatrixRow] = []
    for line in lines[matrix_start + 2 : families_start]:
        if not line.startswith("|") or line.startswith("| Area") or set(line) <= {"|", "-", " "}:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) == MATRIX_COLUMNS:
            rows.append(MatrixRow(cells[0], cells[1], cells[2]))
    must_line = next(
        i for i, line in enumerate(lines) if line.startswith("The architecture MUST be capable")
    )
    families: list[str] = []
    for line in lines[must_line + 2 :]:
        if line.startswith("- "):
            families.append(line[2:].rstrip(";").strip())
        elif families:
            break
    return rows, families


def _check_seed_drift(doc: dict) -> list[Problem]:
    seed = json.loads(SEED_JSON.read_text(encoding="utf-8"))
    if doc == seed:
        return []
    return [
        Problem(
            "seed_drift",
            "capabilities.yaml",
            "checked-in YAML differs from the reviewed seed capabilities.generated.json "
            "(review the change; the registry is never silently overwritten)",
        )
    ]


def _check_duplicate_ids(capabilities: list[dict]) -> list[Problem]:
    seen: set[str] = set()
    problems: list[Problem] = []
    for cap in capabilities:
        if cap["id"] in seen:
            problems.append(Problem("duplicate_id", str(cap["id"]), "registry id appears twice"))
        seen.add(cap["id"])
    return problems


def _check_matrix_row(row: MatrixRow, hits: list[dict], matched: set[str]) -> list[Problem]:
    problems: list[Problem] = []
    if len(hits) != 1:
        problems.append(
            Problem(
                "row_absent" if not hits else "row_duplicated",
                row.area,
                f"parity-matrix row has {len(hits)} registry entr(ies)",
            )
        )
        return problems
    cap = hits[0]
    matched.add(cap["id"])
    expected_class = PRIORITY_TO_CLASSIFICATION.get(_normalize(row.baseline_priority))
    if expected_class is None:
        problems.append(
            Problem(
                "priority_unmapped",
                row.area,
                f"baseline priority {row.baseline_priority!r} has no classification mapping",
            )
        )
    elif cap["classification"] != expected_class:
        problems.append(
            Problem(
                "classification_mismatch",
                row.area,
                f"registry {cap['classification']!r} != priority-derived {expected_class!r} "
                f"(priority {row.baseline_priority!r})",
            )
        )
    return problems


def _check_source_family(family: str, hits: list[dict], matched: set[str]) -> list[Problem]:
    if len(hits) != 1:
        return [
            Problem(
                "family_absent" if not hits else "family_duplicated",
                family,
                f"source family has {len(hits)} registry entr(ies)",
            )
        ]
    matched.add(hits[0]["id"])
    return []


def _check_non_target(cap: dict) -> list[Problem]:
    if cap["id"] not in NON_TARGET_IDS:
        return []
    problems: list[Problem] = []
    if cap["classification"] != "deliberate-non-target":
        problems.append(
            Problem(
                "non_target_misclassified",
                str(cap["id"]),
                f"expected deliberate-non-target, got {cap['classification']!r}",
            )
        )
    if cap["phase"] is not None or cap["implemented"] or cap["enabled"]:
        problems.append(
            Problem(
                "non_target_not_inert",
                str(cap["id"]),
                "non-target must keep phase null, implemented=false, enabled=false",
            )
        )
    return problems


def check_capabilities(repo_root: Path = REPO_ROOT) -> list[Problem]:
    """Full registry gate; return all findings (empty = conformant)."""
    problems: list[Problem] = []
    doc = load_registry(repo_root / "packages" / "contracts" / "capabilities.yaml")
    problems.extend(validate_registry_schema(doc))
    problems.extend(_check_seed_drift(doc))

    capabilities: list[dict] = doc.get("capabilities", [])
    problems.extend(_check_duplicate_ids(capabilities))

    by_name: dict[str, list[dict]] = {}
    for cap in capabilities:
        by_name.setdefault(_normalize(cap["name"]), []).append(cap)

    rows, families = parse_frozen_chapter()
    matched: set[str] = set()
    for row in rows:
        problems.extend(_check_matrix_row(row, by_name.get(_normalize(row.area), []), matched))
    for family in families:
        problems.extend(_check_source_family(family, by_name.get(_normalize(family), []), matched))

    for cap in capabilities:
        if cap["id"] not in matched and cap["id"] not in NON_TARGET_IDS:
            problems.append(
                Problem(
                    "unmatched_entry",
                    str(cap["id"]),
                    "registry entry has no frozen ch02 matrix row / source family origin",
                )
            )
        problems.extend(_check_non_target(cap))

    non_targets = [cap for cap in capabilities if cap["id"] in NON_TARGET_IDS]
    if len(non_targets) != len(NON_TARGET_IDS):
        problems.append(
            Problem(
                "non_target_count",
                "deliberate-non-targets",
                f"expected {len(NON_TARGET_IDS)} non-target entries, found {len(non_targets)}",
            )
        )
    return problems


MIN_CLI_ARGS = 2


def main(argv: list[str]) -> int:
    """CLI entry point: --check runs the registry gate, exit 0 on conformance."""
    if len(argv) < MIN_CLI_ARGS or argv[1] != "--check":
        print("usage: check_capabilities.py --check", file=sys.stderr)
        return 2
    problems = check_capabilities()
    if problems:
        for problem in problems:
            print(f"FAIL {problem.kind}: {problem.subject} — {problem.detail}", file=sys.stderr)
        print(f"{len(problems)} capability registry finding(s)", file=sys.stderr)
        return 1
    doc = load_registry()
    print(
        f"capability registry OK ({len(doc['capabilities'])} entries; "
        "frozen ch02 table reparsed, seed and schema validated)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
