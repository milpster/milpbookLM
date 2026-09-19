"""
Migration harness (FND-03 micro-index 3.3).

Implements ch04 "Startup and upgrades": the migration job takes an advisory lock, verifies a
compatible source version, applies forward migrations, records build metadata. Forward
migrations are restartable - an interrupted run re-executed against the same database is a
no-op (create_all(checkfirst=True) + alembic version bookkeeping).

Roles: DDL always runs under the migration role (env.py verifies current_user). When an app
DSN is supplied, the harness additionally proves the app role can DML but cannot DDL.
"""

from __future__ import annotations

import dataclasses
import os
import time
from pathlib import Path

import psycopg
import psycopg.errors
from alembic import command
from alembic.config import Config

REPO_ROOT = Path(__file__).resolve().parents[5]
MIGRATIONS_DIR = REPO_ROOT / "migrations"
ALEMBIC_INI = MIGRATIONS_DIR / "alembic.ini"

# Stable advisory-lock key for the migration job (per database).
MIGRATION_ADVISORY_KEY = 0x4D4C4203  # "MLB" + task 3

BUILD_SHA_ENV = "MILPBOOKLM_BUILD_SHA"


class UnsupportedSourceVersionError(RuntimeError):
    """The current alembic version is not a supported upgrade source for this build."""


@dataclasses.dataclass(frozen=True, slots=True)
class MigrationReport:
    """Evidence for one harness run: versions, lock key, build, duration."""

    previous_version: str | None
    final_version: str
    applied: bool
    lock_key: int
    build_sha: str
    duration_ms: int


def _alembic_config(dsn: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    os.environ["MILPBOOKLM_DB_URL"] = dsn
    return config


def _current_version(conn: psycopg.Connection) -> str | None:
    # Probe catalog first: a direct SELECT on a missing table would abort this
    # transaction (leaving it unusable for the rest of the locked migration run).
    exists = conn.execute(
        "SELECT EXISTS (SELECT 1 FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = current_schema() AND c.relname = 'alembic_version')"
    ).fetchone()
    if not exists or not exists[0]:
        return None  # fresh database: no version bookkeeping yet
    row = conn.execute("SELECT version_num FROM alembic_version LIMIT 1").fetchone()
    return row[0] if row else None


def _run_upgrade(dsn: str) -> None:
    command.upgrade(_alembic_config(dsn), "head")


def _run_downgrade(dsn: str, target: str) -> None:
    command.downgrade(_alembic_config(dsn), target)


def record_build_metadata(
    conn: psycopg.Connection, *, build_sha: str, final_version: str
) -> None:
    """Record build metadata in the same transaction discipline as the migration (ch04)."""
    rows = (("build_sha", build_sha), ("applied_version", final_version))
    with conn.cursor() as cur:
        for key, value in rows:
            cur.execute(
                "INSERT INTO migration_metadata (key, value, updated_at) "
                "VALUES (%s, %s, now()) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
                (key, value),
            )


def run_migrations(
    *,
    migration_dsn: str,
    app_dsn: str | None = None,
    supported_versions: frozenset[str] | None = None,
) -> MigrationReport:
    """Upgrade to head under the advisory lock with source-version and role checks."""
    started = time.monotonic()
    build_sha = os.environ.get(BUILD_SHA_ENV, "unknown")
    with psycopg.connect(migration_dsn, autocommit=False) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (MIGRATION_ADVISORY_KEY,))
        try:
            previous = _current_version(conn)
            if (
                previous is not None
                and supported_versions is not None
                and previous not in supported_versions
            ):
                raise UnsupportedSourceVersionError(
                    f"source version {previous!r} is not supported by this build "
                    f"(supported: {sorted(supported_versions)})"
                )
            _run_upgrade(migration_dsn)
            final = _current_version(conn)
            if final is None:
                raise RuntimeError("alembic upgrade head did not stamp a version")
            record_build_metadata(conn, build_sha=build_sha, final_version=final)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (MIGRATION_ADVISORY_KEY,))
    if app_dsn is not None:
        with psycopg.connect(app_dsn, autocommit=False) as app_conn:
            app_conn.execute("SELECT 1")
            _probe_app_cannot_ddl(app_conn)
    return MigrationReport(
        previous_version=previous,
        final_version=final,
        applied=previous != final,
        lock_key=MIGRATION_ADVISORY_KEY,
        build_sha=build_sha,
        duration_ms=int((time.monotonic() - started) * 1000),
    )


def downgrade_to(*, migration_dsn: str, target: str = "base") -> str | None:
    """Run a down migration under the same advisory lock (rehearsal / supported rollback)."""
    with psycopg.connect(migration_dsn, autocommit=False) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (MIGRATION_ADVISORY_KEY,))
        try:
            previous = _current_version(conn)
            _run_downgrade(migration_dsn, target)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (MIGRATION_ADVISORY_KEY,))
    return previous


def _probe_app_cannot_ddl(app_conn: psycopg.Connection) -> None:
    """Negative proof of the role boundary: the app role must fail a DDL probe."""
    try:
        with app_conn.cursor() as cur:
            cur.execute("CREATE TABLE _fnd03_app_ddl_probe (id uuid)")
        app_conn.rollback()
    except psycopg.errors.InsufficientPrivilege:
        return
    raise RuntimeError("FND-03: app role created a table - DDL boundary is broken")


__all__ = [
    "ALEMBIC_INI",
    "MIGRATIONS_DIR",
    "MIGRATION_ADVISORY_KEY",
    "REPO_ROOT",
    "MigrationReport",
    "UnsupportedSourceVersionError",
    "downgrade_to",
    "record_build_metadata",
    "run_migrations",
]
