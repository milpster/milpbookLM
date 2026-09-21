#!/usr/bin/env bash
set -euo pipefail

api_origin="${MILPBOOKLM_API_ORIGIN:-http://127.0.0.1:8000}"
curl --fail --silent --show-error "$api_origin/health/live" >/dev/null
exec pnpm dev
