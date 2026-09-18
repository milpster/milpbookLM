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

# --- pinned toolchain, self-contained (no ambient-PATH assumptions) ---------
# Fresh shells put other toolchains first on PATH (pi-node v22 under
# ~/.local/share/pi-node, /usr/bin/node v20) and often lack uv entirely.
# ci/run.sh owns its toolchain: it pins this node install, prepends it,
# self-heals it from the official tarball if missing, and resolves uv from
# the local install when the ambient PATH has no uv.
NODE_HOME="$HOME/.local/node/node-v24.21.0-linux-x64"
if [ ! -x "$NODE_HOME/bin/node" ]; then
  mkdir -p "$NODE_HOME"
  curl -fsSL "https://nodejs.org/dist/v24.21.0/node-v24.21.0-linux-x64.tar.xz" \
    | tar -xJ --strip-components=1 -C "$NODE_HOME"
fi
export PATH="$NODE_HOME/bin:$PATH"
export COREPACK_ENABLE_DOWNLOAD_PROMPT=0
if [ ! -e "$NODE_HOME/bin/pnpm" ]; then
  "$NODE_HOME/bin/corepack" enable --install-directory "$NODE_HOME/bin"
fi
if ! command -v uv >/dev/null 2>&1; then
  for candidate in "$HOME"/.pyenv/versions/*/bin/uv "$HOME"/.local/bin/uv; do
    if [ -x "$candidate" ]; then
      export PATH="$(dirname "$candidate"):$PATH"
      break
    fi
  done
fi
command -v uv >/dev/null 2>&1 || { echo "uv not found (tried PATH, pyenv, ~/.local/bin)"; exit 1; }

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
