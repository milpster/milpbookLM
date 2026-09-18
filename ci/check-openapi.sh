#!/usr/bin/env bash
# OpenAPI placeholder gate (FND-01): the contract document must exist and be a
# structurally valid OpenAPI 3.1 stub. Full validation + TS client generation
# lands with the API capability tasks (REFERENCE-DEPENDENCIES: "generation
# runs in CI").
set -euo pipefail
cd "$(dirname "$0")/.."

SPEC=packages/contracts/openapi.yaml
test -s "$SPEC"
grep -q '^openapi: "3.1.0"' "$SPEC"
grep -q '^info:' "$SPEC"
grep -q '^paths:' "$SPEC"
grep -q '^components:' "$SPEC"
echo "openapi.yaml: valid OpenAPI 3.1 stub"
