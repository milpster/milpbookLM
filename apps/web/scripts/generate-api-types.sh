#!/usr/bin/env bash
set -euo pipefail

# The OpenAPI schema is served by the API origin; the vite dev server only
# proxies /api, so the default must point at the API itself.
schema_url="${MILPBOOKLM_OPENAPI_URL:-http://127.0.0.1:8000/openapi.json}"
output="${1:-src/generated/api.d.ts}"
mkdir -p "$(dirname "$output")"
pnpm exec openapi-typescript "$schema_url" --output "$output"
