#!/usr/bin/env bash
# Local mirror of .github/workflows/ci.yml (FND-01).
#
# Orchestrator-approved interpretation: this repository has no git remote and
# no CI runner, so the PR pipeline is executed natively by this script. Every
# step below maps 1:1 to a step in ci.yml (same commands, same order).
#
# Exit 0 = pipeline green. Run: ci/run.sh  (from any directory).
set -euo pipefail
cd "$(dirname "$0")/.."

# --- pinned toolchain -------------------------------------------------------
NODE_REQUIRED="v24.21.0"
PNPM_REQUIRED="12.4.2"

step() { printf '\n=== %s\n' "$*"; }

step "0. toolchain (pinned versions)"
node --version
pnpm --version
uv --version
uv run python --version
[ "$(node --version)" = "$NODE_REQUIRED" ] || { echo "node is $(node --version), required $NODE_REQUIRED"; exit 1; }
[ "$(pnpm --version)" = "$PNPM_REQUIRED" ] || { echo "pnpm is $(pnpm --version), required $PNPM_REQUIRED"; exit 1; }

step "1. frozen installs"
# --all-packages: the virtual root has no deps of its own; install all
# workspace members so import-linter/pytest see the full package graph.
uv sync --frozen --all-packages
pnpm install --frozen-lockfile

step "2. lint"
uv run ruff check .
uv run ruff format --check .
pnpm exec biome check .

step "3. type"
uv run mypy
pnpm exec tsc --build --force

step "4. import-graph (layering, forbidden imports, cycles)"
uv run import-linter lint

step "5. conformance + architecture + meta (VER-mapped)"
uv run python tools/spec/emit_conformance.py
uv run pytest tests/architecture tests/meta -v

step "6. unit"
uv run pytest tests/unit -v
pnpm exec vitest run

step "7. openapi placeholder (structural gate; generation lands with API tasks)"
bash ci/check-openapi.sh

step "ALL CHECKS PASSED"
