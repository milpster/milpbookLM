#!/usr/bin/env bash
# Idempotent local dev-database bootstrap for milpbookLM.
#
# Brings up the PostgreSQL 17 dev cluster, ensures the `milpbooklm` database,
# applies migrations/roles.sql, resets both dev roles to the passwords
# documented in migrations/roles.sql, and (re)writes the agent DSN file
# consumed by .opencode/opencode.json ({file:...} interpolation).
#
# Usage (once, from anywhere):
#   sudo tools/dev-db-bootstrap.sh
#
# Optional: allow the coding agent to run this autonomously by adding a
# sudoers rule (visudo):
#   srcds ALL=(root) NOPASSWD: /home/srcds/dev/milpbookLM/tools/dev-db-bootstrap.sh
#
# Safe to re-run: every step is idempotent.
set -euo pipefail

DB_NAME="milpbooklm"
DSN_FILE="$(cd "$(dirname "$0")/.." && pwd)/.opencode/dev-database-uri"
APP_ROLE="milpbooklm_app"
MIGRATION_ROLE="milpbooklm_migration"
APP_PASSWORD="milpbooklm_app"       # documented dev default in migrations/roles.sql
MIGRATION_PASSWORD="milpbooklm_migration"

if [[ "${EUID}" -ne 0 ]]; then
  echo "ERROR: run via sudo (needs the postgres OS user + service control)." >&2
  exit 1
fi

psql_as_postgres() {
  sudo -u postgres psql -v ON_ERROR_STOP=1 -q "$@"
}

# 1. Ensure the cluster is up (dev box service; start if stopped).
if ! pg_isready -q -h 127.0.0.1 -p 5432; then
  pg_ctlcluster 17 main start
fi

# 2. Ensure the database exists.
if ! psql_as_postgres -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '${DB_NAME}'" | grep -q 1; then
  sudo -u postgres createdb "${DB_NAME}"
fi

# 3. Roles + grants (roles.sql is idempotent: IF NOT EXISTS).
psql_as_postgres -d "${DB_NAME}" -f "$(dirname "$0")/../migrations/roles.sql"

# 4. Force dev passwords to the documented defaults (roles.sql keeps
#    pre-existing passwords; this makes the bootstrap deterministic).
psql_as_postgres -d postgres <<SQL
ALTER ROLE ${APP_ROLE} WITH LOGIN PASSWORD '${APP_PASSWORD}';
ALTER ROLE ${MIGRATION_ROLE} WITH LOGIN PASSWORD '${MIGRATION_PASSWORD}';
SQL

# 5. Write the agent DSN file (owned by the invoking user, mode 600).
install -D -m 600 /dev/null "${DSN_FILE}"
printf 'postgresql://%s:%s@127.0.0.1:5432/%s\n' "${APP_ROLE}" "${APP_PASSWORD}" "${DB_NAME}" > "${DSN_FILE}"
if [[ -n "${SUDO_UID:-}" ]]; then
  chown "${SUDO_UID}:${SUDO_GID:-${SUDO_UID}}" "${DSN_FILE}"
fi

echo "OK: database='${DB_NAME}' roles reset, DSN written to ${DSN_FILE}"
echo "Next: restart opencode; the postgres MCP reads the DSN file automatically."
