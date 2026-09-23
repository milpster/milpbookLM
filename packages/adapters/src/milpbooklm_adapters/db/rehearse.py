"""
Destructive-migration rehearsal (FND-03 micro-index 3.3.2, ch04 "Startup and upgrades").

ch04: "Rollback uses restored backups or an explicitly supported down migration; destructive
migration rehearsals are mandatory." For the baseline release the previous supported release
is the empty schema, so the rehearsal proves the full destructive cycle on a real PG18:

  head -> downgrade base (drops every table, the destructive step) -> verify empty
  -> upgrade head -> verify the complete ch05 schema + immutability triggers again

Exits 0 with a PASS report only if every step held; the report JSON is printed to stdout
(evidence for the VER batch) and a copy is written next to the log by the caller.
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
import time
import uuid

import psycopg

from .harness import _current_version, current_script_head, downgrade_to, run_migrations
from .schema import METADATA
from .triggers import TRIGGER_DDL

EXPECTED_TABLES = frozenset(METADATA.tables)


class RehearsalStepFailureError(RuntimeError):
    """A rehearsal step failed; the report records which one."""


@dataclasses.dataclass(frozen=True, slots=True)
class RehearsalReport:
    """Outcome of the destructive rehearsal cycle (evidence for the VER batch)."""

    outcome: str
    steps: tuple[tuple[str, str], ...]
    duration_ms: int
    database: str


def _step(steps: list[tuple[str, str]], name: str, ok: bool, detail: str = "") -> None:
    status = "pass" if ok else "fail"
    steps.append((name, status if not detail else f"{status}: {detail}"))
    if not ok:
        raise RehearsalStepFailureError(f"{name}: {detail}")


def _table_names(conn: psycopg.Connection) -> frozenset[str]:
    rows = conn.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
        "AND tablename <> 'alembic_version'"
    ).fetchall()
    return frozenset(r[0] for r in rows)


def _first(row: tuple[object, ...] | None) -> object:
    return row[0] if row is not None else None


def _trigger_count(conn: psycopg.Connection) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM pg_trigger WHERE NOT tgisinternal"
    ).fetchone()
    return int(row[0]) if row is not None else 0


def run_rehearsal(
    *, migration_dsn: str, app_dsn: str | None = None, build_sha: str = "unknown"
) -> RehearsalReport:
    """Execute the full destructive rehearsal cycle against the target database."""
    started = time.monotonic()
    steps: list[tuple[str, str]] = []
    db_name = migration_dsn.rsplit("/", 1)[-1].rsplit("@", maxsplit=1)[-1]
    try:
        with psycopg.connect(migration_dsn) as conn:
            head_version = _current_version(conn)
            expected_head = current_script_head()
            _step(
                steps,
                "record_head",
                head_version == expected_head,
                f"head={head_version!r} expected={expected_head!r}",
            )

        # Destructive step: downgrade to base (previous supported release = empty schema).
        downgrade_to(migration_dsn=migration_dsn, target="base")
        with psycopg.connect(migration_dsn) as conn:
            remaining = _table_names(conn)
            _step(steps, "downgrade_base", not remaining, f"remaining={sorted(remaining)}")
            _step(steps, "triggers_gone", _trigger_count(conn) == 0)

        # Forward again: the schema must come back complete and identical.
        report = run_migrations(migration_dsn=migration_dsn, app_dsn=app_dsn)
        with psycopg.connect(migration_dsn) as conn:
            tables = _table_names(conn)
            _step(
                steps,
                "upgrade_head",
                tables == EXPECTED_TABLES,
                f"missing={sorted(EXPECTED_TABLES - tables)}",
            )
            _step(steps, "version_at_head", report.final_version == current_script_head())
            trigger_count = _trigger_count(conn)
            _step(
                steps,
                "triggers_restored",
                trigger_count >= len(TRIGGER_DDL),
                f"count={trigger_count}",
            )
            # Immutability spot-check: a canonical document update must be rejected.
            user = _first(
                conn.execute(
                    "INSERT INTO users (id, email, display_name, password_hash) "
                    "VALUES (%s, %s, %s, %s) RETURNING id",
                    (uuid.uuid4(), "rehearsal@example.invalid", "Rehearsal", "x"),
                ).fetchone()
            )
            notebook = _first(
                conn.execute(
                    "INSERT INTO notebooks (id, title, created_by_user_id) "
                    "VALUES (%s, %s, %s) RETURNING id",
                    (uuid.uuid4(), "Rehearsal notebook", user),
                ).fetchone()
            )
            source = _first(
                conn.execute(
                    "INSERT INTO sources (id, notebook_id, type, origin, display_title, "
                    "created_by_user_id) VALUES (%s, %s, 'plain_text', 'rehearsal://x', "
                    "'Rehearsal source', %s) RETURNING id",
                    (uuid.uuid4(), notebook, user),
                ).fetchone()
            )
            version = _first(
                conn.execute(
                    "INSERT INTO source_versions (id, source_id, version_number, content_sha256, "
                    "status, activated_at, created_by_user_id) "
                    "VALUES (%s, %s, 1, 'aa' || repeat('0', 62), 'active', now(), %s) RETURNING id",
                    (uuid.uuid4(), source, user),
                ).fetchone()
            )
            doc = _first(
                conn.execute(
                    "INSERT INTO canonical_documents (id, source_version_id, "
                    "canonical_schema_version, parser_identity, parser_version, "
                    "parser_profile, tool_versions, contract_json) "
                    "VALUES (%s, %s, '1', 'rehearsal', '1', 'rehearsal', '{}'::jsonb, "
                    "'{}'::jsonb) RETURNING id",
                    (uuid.uuid4(), version),
                ).fetchone()
            )
            conn.commit()
            try:
                conn.execute(
                    "UPDATE canonical_documents SET parser_version = '2' WHERE id = %s",
                    (doc,),
                )
                conn.rollback()
                _step(
                    steps,
                    "immutability_enforced",
                    False,
                    "update on canonical_documents was allowed",
                )
            except psycopg.Error:
                conn.rollback()
                _step(steps, "immutability_enforced", True)
    except RehearsalStepFailureError as exc:
        steps.append(("aborted", f"fail: {exc}"))
        return RehearsalReport(
            outcome="FAIL",
            steps=tuple(steps),
            duration_ms=int((time.monotonic() - started) * 1000),
            database=db_name,
        )
    return RehearsalReport(
        outcome="PASS",
        steps=tuple(steps),
        duration_ms=int((time.monotonic() - started) * 1000),
        database=db_name,
    )


def main(argv: list[str]) -> int:
    """CLI entry point: read DSNs from the environment, print the report JSON."""
    migration_dsn = os.environ.get("MILPBOOKLM_MIGRATION_DSN", "")
    app_dsn = os.environ.get("MILPBOOKLM_APP_DSN", "") or None
    if not migration_dsn:
        print("MILPBOOKLM_MIGRATION_DSN is required", file=sys.stderr)
        return 2
    report = run_rehearsal(migration_dsn=migration_dsn, app_dsn=app_dsn)
    print(json.dumps(dataclasses.asdict(report), indent=2))
    return 0 if report.outcome == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
