"""
Alembic environment with the FND-03 app/migration connection split (micro-index 3.2.2).

Role split (ch04 + REFERENCE-DEPENDENCIES "migrations use a separate privileged DB role"):

* ``MILPBOOKLM_DB_URL``      - DSN used for DDL. MUST be the migration role.
* ``MILPBOOKLM_MIGRATION_ROLE`` - expected role name (default ``milpbooklm_migration``);
  env.py verifies ``current_user`` and refuses to run DDL under any other role (e.g. app).
* ``MILPBOOKLM_APP_URL``     - optional app-role DSN. When present, env.py proves the
  app role can SELECT/INSERT but CANNOT DDL, and closes it before DDL runs.

Forward migrations run inside one connection/transaction per revision, making them
restartable (re-running an applied revision is a no-op via ``checkfirst`` semantics in
the baseline and alembic's version bookkeeping).
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from milpbooklm_adapters.db.schema import METADATA
from sqlalchemy import create_engine, text

CONFIG = context.config
if CONFIG.config_file_name is not None:
    fileConfig(CONFIG.config_file_name)

DEFAULT_MIGRATION_ROLE = "milpbooklm_migration"


def _dsn_env(var: str) -> str:
    value = os.environ.get(var, "").strip()
    if not value:
        raise SystemExit(f"FND-03: environment variable {var} is required for migrations")
    return value


def _verify_migration_role(url: str) -> None:
    """Refuse DDL unless the connection is the privileged migration role."""
    expected = os.environ.get("MILPBOOKLM_MIGRATION_ROLE", DEFAULT_MIGRATION_ROLE)
    with create_engine(url).connect() as conn:
        current = conn.execute(text("SELECT current_user")).scalar_one()
    if current != expected:
        raise SystemExit(
            f"FND-03: refusing DDL: current_user={current!r} is not the migration role "
            f"{expected!r} (app role must never run migrations)"
        )


def _verify_app_role_is_ddl_free(app_url: str) -> None:
    """Positive probe (app can DML) + negative probe (app cannot DDL)."""
    engine = create_engine(app_url)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    with engine.connect() as conn:
        try:
            conn.execute(text("CREATE TABLE _fnd03_app_ddl_probe (id uuid)"))
            conn.rollback()
        except Exception as exc:
            if "permission denied" not in str(exc).lower():
                raise SystemExit(f"FND-03: unexpected app-role DDL probe failure: {exc}") from exc
        else:
            raise SystemExit("FND-03: app role CAN create tables - role DDL boundary is broken")
    engine.dispose()


def _sa_url(dsn: str) -> str:
    """Map the psycopg3-native scheme to SQLAlchemy's psycopg dialect driver."""
    return dsn.replace("postgresql://", "postgresql+psycopg://", 1)


def run_migrations(url: str) -> None:
    """Configure the migration bind and run upgrade/downgrade per the alembic context."""
    url = _sa_url(url)
    _verify_migration_role(url)
    app_url = os.environ.get("MILPBOOKLM_APP_URL", "").strip()
    if app_url:
        _verify_app_role_is_ddl_free(_sa_url(app_url))
    connectable = create_engine(url)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=METADATA,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


# Module-level call: alembic loads this file as a module (__name__ != "__main__"),
# so the migration entrypoint must NOT be guarded by a __main__ check.
run_migrations(_dsn_env("MILPBOOKLM_DB_URL"))
