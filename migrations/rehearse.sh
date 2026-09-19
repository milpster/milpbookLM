#!/usr/bin/env bash
# FND-03 destructive-migration rehearsal runner (ch04: rehearsals are mandatory).
# Requires MILPBOOKLM_MIGRATION_DSN (and optionally MILPBOOKLM_APP_DSN) in the environment.
# Prints the PASS/FAIL report JSON; exits non-zero on FAIL.
set -euo pipefail
cd "$(dirname "$0")/.."
exec uv run python -m milpbooklm_adapters.db.rehearse "$@"
