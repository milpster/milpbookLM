#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  printf 'usage: %s EMAIL\n' "$0" >&2
  exit 2
fi

database_url="${MILPBOOKLM_SEED_DATABASE_URL:-postgresql://srcds@/milpbooklm_t13?host=/home/srcds/dev/milpbookLM/scratch/t13-smoke&port=29521}"
email="$1"
psql "$database_url" -v ON_ERROR_STOP=1 -v email="$email" <<'SQL'
WITH actor AS (
  SELECT id FROM users WHERE email = lower(:'email')
), created AS (
  INSERT INTO notebooks (id, title, owner_user_id, created_by_user_id)
  SELECT uuidv7(), 'Task 18 smoke notebook', id, id FROM actor
  RETURNING id, owner_user_id
)
INSERT INTO notebook_memberships (notebook_id, user_id, role)
SELECT id, owner_user_id, 'owner' FROM created
ON CONFLICT DO NOTHING;
SQL
