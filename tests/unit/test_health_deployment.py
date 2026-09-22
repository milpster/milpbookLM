"""Stale-constant guards for deployment health (ch04/ch05, schema head + PG major).

Given:  the migrations package and the deployment-health constants.
When:   a new migration lands or the production PG default changes.
Then:   the schema-head constant still equals the actual migration head (it is
        derived, never hardcoded), and the PG major floor stays overridable.
"""

from __future__ import annotations

import re
from pathlib import Path

from milpbooklm_api.health_routes import EXPECTED_SCHEMA_REVISION, REQUIRED_POSTGRES_MAJOR

REPO_ROOT = Path(__file__).resolve().parents[2]
VERSIONS_DIR = REPO_ROOT / "migrations" / "versions"
PRODUCTION_POSTGRES_MAJOR = 18

# Independent of alembic: parse the revision graph straight from the version
# files so a broken head derivation cannot validate itself.
_REVISION = re.compile(r'^revision(?::\s*str)?\s*=\s*["\'](\w+)["\']', re.MULTILINE)
_DOWN_REVISION = re.compile(r'^down_revision(?::[^=\n]*)?\s*=\s*["\'](\w+)["\']', re.MULTILINE)


def _migration_heads() -> frozenset[str]:
    revisions: set[str] = set()
    parents: set[str] = set()
    for path in sorted(VERSIONS_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        source = path.read_text(encoding="utf-8")
        revision = _REVISION.search(source)
        assert revision is not None, f"{path.name}: no revision assignment"
        revisions.add(revision.group(1))
        parents.update(_DOWN_REVISION.findall(source))
    return frozenset(revisions - parents)


def test_expected_schema_revision_tracks_actual_migration_head() -> None:
    heads = _migration_heads()
    assert len(heads) == 1, f"migration graph must have exactly one head: {sorted(heads)}"
    assert EXPECTED_SCHEMA_REVISION in heads, (
        f"EXPECTED_SCHEMA_REVISION {EXPECTED_SCHEMA_REVISION!r} is stale; "
        f"actual migration head: {sorted(heads)}"
    )


def test_required_postgres_major_stays_the_production_default() -> None:
    assert REQUIRED_POSTGRES_MAJOR == PRODUCTION_POSTGRES_MAJOR
