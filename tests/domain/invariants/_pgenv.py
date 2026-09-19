"""Shared PG18 runtime for the FND-03 tests (digest-pinned image, direct binaries).

docker/containerd/runc are all non-functional on this host (capabilities stripped by the
runtime, no newuidmap for rootless idmap - recorded in .omo evidence), so the tests run
the digest-pinned pgvector/pgvector:pg18 binaries straight from the extracted rootfs on
the host glibc 2.41 loader, with the image-only libraries in hostlibs/. A module-level
flag makes the three conftests (domain/invariants, unit/db, contract) launch and tear
down the server exactly once per pytest session.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import psycopg
from milpbooklm_adapters.db import harness

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRATCH = Path(os.environ.get("MILPBOOKLM_PG_SCRATCH", "/run/user/1000/fnd03-ctd"))
POSTGRES_BIN = SCRATCH / "rootfs/usr/lib/postgresql/18/bin/postgres"
PORT = 29517
SUPERUSER_DSN = f"postgresql://postgres@127.0.0.1:{PORT}/postgres"
TEST_DB = "fnd03_test"
APP_DSN = f"postgresql://milpbooklm_app:milpbooklm_app@127.0.0.1:{PORT}/{TEST_DB}"
MIGRATION_DSN = f"postgresql://milpbooklm_migration:milpbooklm_migration@127.0.0.1:{PORT}/{TEST_DB}"

# Shared across the session-scoped pg_env fixtures: launch/kill happen exactly once.
_SESSION: dict[str, bool] = {"started": False}


def _alive() -> bool:
    try:
        with psycopg.connect(SUPERUSER_DSN, connect_timeout=2) as conn:
            conn.execute("SELECT 1")
        return True
    except psycopg.OperationalError:
        return False


def _launch() -> None:
    with (SCRATCH / "pg-run.log").open("ab") as log:
        subprocess.Popen(
            ["setsid", str(SCRATCH / "pg18-launch.sh")],
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )


def _wait_ready(timeout_s: float = 90.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _alive():
            return
        time.sleep(0.5)
    raise RuntimeError(f"PG18 not ready within {timeout_s}s (log: {SCRATCH / 'pg-run.log'})")


def _apply_roles_sql(dbname: str) -> None:
    """Apply the role DDL as superuser. Statement-level 'does not exist' failures are
    tolerated under autocommit (roles.sql is idempotent; e.g. the DATABASE grants fail
    while the named database does not exist yet on a first bootstrap)."""
    sql = (REPO_ROOT / "migrations" / "roles.sql").read_text()
    url = f"{SUPERUSER_DSN.rsplit('/', 1)[0]}/{dbname}"
    with psycopg.connect(url, autocommit=True) as conn:
        try:
            conn.execute(sql)
        except psycopg.Error as exc:
            if "does not exist" not in str(exc):
                raise
            # Re-run statement-by-statement is unnecessary: the roles/extension created
            # before the failing GRANT persist under autocommit.


def _ensure_databases() -> None:
    with psycopg.connect(SUPERUSER_DSN, autocommit=True) as conn:
        for dbname, owner in (("milpbooklm", None), (TEST_DB, "milpbooklm_migration")):
            exists = conn.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)
            ).fetchone()
            if exists is None:
                owner_sql = f" OWNER {owner}" if owner else ""
                conn.execute(f"CREATE DATABASE {dbname}{owner_sql}")


def ensure_pg() -> dict[str, str]:
    """Bring the digest-pinned PG18 to the migrated test state; idempotent."""
    if not _alive():
        _launch()
        _SESSION["started"] = True
    _wait_ready()
    _apply_roles_sql("postgres")
    _ensure_databases()
    _apply_roles_sql("milpbooklm")
    _apply_roles_sql(TEST_DB)
    harness.run_migrations(migration_dsn=MIGRATION_DSN, app_dsn=APP_DSN)
    return {
        "superuser": SUPERUSER_DSN,
        "app": APP_DSN,
        "migration": MIGRATION_DSN,
        "test_db": TEST_DB,
    }


def teardown_pg() -> None:
    """Stop the server only if this session started it (a pre-existing PG is left alone)."""
    if _SESSION["started"]:
        # The launcher execs with a path relative to SCRATCH, so match that form.
        subprocess.run(["pkill", "-f", str(POSTGRES_BIN.relative_to(SCRATCH))], check=False)
        _SESSION["started"] = False
