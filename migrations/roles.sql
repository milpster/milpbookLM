-- FND-03 role DDL (ch04 "Identities and storage", REFERENCE-DEPENDENCIES:
-- "migrations use a separate privileged DB role").
--
-- Applied by the superuser bootstrap (POSTGRES_USER=postgres) on the target database
-- (milpbooklm under compose; the fnd03_test harness DB in the test suite):
--   * milpbooklm_app      - application login role. NO DDL: CONNECT + object DML grants only.
--   * milpbooklm_migration - migration login role. Privileged for schema DDL and extensions.
-- Idempotent: safe to re-run against an existing installation.

-- Required extension (TAD-003: PostgreSQL 18 + pgvector). Created here, at bootstrap, by
-- the superuser: pgvector is NOT a trusted extension, so the (non-superuser) migration role
-- cannot create it. Every migrated database gets it exactly once, before the baseline runs.
CREATE EXTENSION IF NOT EXISTS vector;
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'milpbooklm_app') THEN
    CREATE ROLE milpbooklm_app LOGIN
      PASSWORD 'milpbooklm_app'
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'milpbooklm_migration') THEN
    CREATE ROLE milpbooklm_migration LOGIN
      PASSWORD 'milpbooklm_migration'
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
  END IF;
END
$$;

-- Migration role: full DDL on the schema (owns every migrated object) + CREATE for extensions.
-- GRANT ... ON DATABASE requires a literal name (current_database() is not valid GRANT syntax),
-- so the DATABASE-level grants are issued via dynamic SQL against whichever database this
-- script runs in (milpbooklm under compose; the fnd03_test harness DB in the test suite).
DO $$
BEGIN
  EXECUTE format('GRANT ALL ON DATABASE %I TO milpbooklm_migration', current_database());
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO milpbooklm_app', current_database());
END
$$;
GRANT ALL ON SCHEMA public TO milpbooklm_migration;

-- App role: connect + read the schema; DML grants on objects arrive with each migration
-- (baseline upgrade grants them in a role-guarded DO block, so no DDL is ever needed here).
GRANT USAGE ON SCHEMA public TO milpbooklm_app;
