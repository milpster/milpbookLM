"""Connection helpers for the two-role Postgres split (FND-03 micro-index 3.2.2)."""

from __future__ import annotations

import os

import sqlalchemy as sa

ENV_APP_DSN = "MILPBOOKLM_APP_DSN"
ENV_MIGRATION_DSN = "MILPBOOKLM_MIGRATION_DSN"


def app_dsn() -> str:
    """Application-role DSN (DML only; the env guard refuses to let it run DDL)."""
    value = os.environ.get(ENV_APP_DSN, "").strip()
    if not value:
        raise RuntimeError(f"{ENV_APP_DSN} is not set")
    return value


def migration_dsn() -> str:
    """Privileged migration-role DSN (the only role allowed to run alembic)."""
    value = os.environ.get(ENV_MIGRATION_DSN, "").strip()
    if not value:
        raise RuntimeError(f"{ENV_MIGRATION_DSN} is not set")
    return value


def make_engine(dsn: str) -> sa.engine.Engine:
    """Provide a sync engine for psycopg 3 with a small, explicit pool (harness scale)."""
    return sa.create_engine(
        dsn,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
    )
