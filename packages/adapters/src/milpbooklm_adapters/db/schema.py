"""
The ch05 schema as a single SQLAlchemy MetaData (FND-03).

This MetaData is the single source of truth for the alembic baseline revision AND for the
schema-completeness checks: the baseline does ``METADATA.create_all`` / ``drop_all`` plus
the immutability triggers, so no DDL can drift between tests and migrations.
"""

from __future__ import annotations

from . import tables  # noqa: F401 - importing tables registers them on METADATA
from .tables._common import METADATA
from .triggers import TRIGGER_DDL, TRIGGER_FUNCTIONS, drop_triggers_sql

__all__ = [
    "APP_ROLE_GRANT_DDL",
    "METADATA",
    "TRIGGER_DDL",
    "TRIGGER_FUNCTIONS",
    "drop_triggers_sql",
]

# Role DDL boundary (FND-03 micro-index 3.2.1): after each migration the app role gets
# DML on the objects it may touch. Guarded so a database without the app role (e.g. a
# scratch test DB) still migrates cleanly.
APP_ROLE_GRANT_DDL = """
DO $$
BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'milpbooklm_app') THEN
    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO milpbooklm_app;
    GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO milpbooklm_app;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public
      GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO milpbooklm_app;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public
      GRANT USAGE ON SEQUENCES TO milpbooklm_app;
  END IF;
END
$$;
"""
