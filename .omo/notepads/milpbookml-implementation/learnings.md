# Learnings — milpbookml-implementation

Conventions, patterns, and successful approaches discovered during work on this plan.

_Auto-scaffolded by /start-work. Append new entries below - never overwrite._

---

## FND-01 (2026-09-18)

1. **import-linter 2.15 config format**: contracts live in an array `[[tool.importlinter.contracts]]`, NOT old `[tool.importlinter.contract:name]` tables (tables parse but yield 0 contracts). `forbidden` contracts use `source_modules` (not `modules`); `independence` uses `modules`; `layers` uses `layers`. Forbidding external framework modules (fastapi, ...) additionally requires `include_external_packages = true` at top level, or the run aborts with "must have include_external_packages=True". CLI needs the explicit subcommand: `uv run import-linter lint`.

2. **uv workspace + virtual root**: the monorepo root is `[tool.uv] package = false` with zero own deps, so plain `uv sync --frozen` installs almost nothing — use `uv sync --frozen --all-packages` so all six workspace members land in the venv (import-linter and pytest need the installed graph).

3. **pytest collection vs spec-mandated test paths**: `requirements.generated.json` mandates test files like `ver-arch-01-001.py`, which the default `python_files = test_*.py` pattern never collects (0 items, exit 5). Fixed via `python_files = ["test_*.py", "ver-*.py"]` in `[tool.pytest.ini_options]`.

4. **Biome 2.x scope discipline**: `biome check .` formats EVERYTHING, including orchestrator state (`.omo/`), generated evidence (`artifacts/`) and the fingerprinted normative guide — reformatting the guide would break ledger fingerprints. Excluded all three via `files.includes` negations; run `biome migrate --write` when the CLI version outgrows the `$schema` (2.0.0 → 2.5.14, `recommended` → `preset`).

5. **TS const + same-name type export**: `export type { X }` + `export { X }` for a const-with-type-alias `X` is a duplicate identifier (TS2300) because a plain `export { X }` carries both meanings. Keep the value re-export alone; drop X from the type-only list. Also: biome's organize-imports assist is the safe way to get `verbatimModuleSyntax`-clean import ordering (`type`-specifier first).

6. **pnpm strict layout + project references**: workspace deps are symlinked only into the CONSUMER's node_modules. If `apps/web` imports `@milpbooklm/web-domain` types directly, it must declare `@milpbooklm/web-domain: workspace:*` in its own package.json (and `pnpm install` to update the lock) — otherwise `tsc --build` fails TS2307 even with correct `references`.

7. **CI scripts must own their toolchain PATH — ambient PATH is untrustworthy**: the first `ci/run.sh` pass was a false green: my session had `~/.local/node/current/bin` exported, but a fresh shell resolves `node` to pi-node v22.23.1 (its bin dir comes FIRST in PATH, before `~/.local/bin`) or to `/usr/bin/node` v20.18.1 (login shell), and `uv` (a pyenv shim at `~/.pyenv/shims/uv`) is absent from non-interactive PATHs entirely. Fix: `ci/run.sh` pins `NODE_HOME=$HOME/.local/node/node-v24.21.0-linux-x64` (self-heals from the official tarball if missing), prepends `$NODE_HOME/bin`, and resolves the real uv binary from `~/.pyenv/versions/*/bin/uv` when `command -v uv` fails. Verified with `env -i` clean login shell AND a pi-node-first PATH — both exit 0. Never assert a tool version in CI without first owning its PATH resolution.
