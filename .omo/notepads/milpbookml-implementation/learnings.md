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

---

## FND-02 (2026-09-18)

1. **spec census fingerprint/anchor semantics**: the fingerprint (SHA-256 of source+term+occurrence_on_line+whitespace-normalized statement) deliberately EXCLUDES the line number, so the ledger can survive reflow; line movement is caught only by comparing the anchor (line, occurrence_on_line) of the fingerprint-matched occurrence. Consequence: a -1/+1 mutation that nets zero movement is by design invisible — mutation QA must use insert-only probes. Exact rescan recipe that reproduces all 507 fingerprints: files = guide top-level `[0-2][0-9]-*.md` + `architecture-baseline/[0-2][0-9]-*.md`; regex `\bMUST NOT\b|\bMUST\b|\bSHOULD NOT\b|\bSHOULD\b` IGNORECASE (longest-first), finditer per line, 1-based line and occurrence.

2. **frozen ch02 table: the `Area` column, not `Target capability`, is the identity**: registry `name` maps to the table's Area column; matching on the Target capability column fails 43/43. `reference_text` is a curated approximation of the Target capability cell (e.g. `public_notebooks` differs), so the reparse gate asserts presence/uniqueness + priority→classification only — never byte-equality of reference text. Priority→classification keys are normalized with `re.sub(r'[^a-z0-9]+','',s.lower())`.

3. **shared working tree with a sibling task**: import-linter (and the task-1 import-linter tests) abort with "Syntax error in <untracked sibling WIP file>" while sibling task 3 edits `packages/adapters/` in the same tree. A boundary test must distinguish: "Contract violated" in output = always fail; "Syntax error in" = evaluation blocked, fall back to asserting the frozen contracts are still declared in pyproject.toml (CI's clean checkout re-runs full enforcement). Also: `uv run mypy` over the whole workspace fails on the sibling's broken file — verify owned code with `uv run mypy --package <pkg>`.

4. **script mains and tools-as-modules**: `main(argv)` must check `argv[1:]` (argv[0] is the script path — off-by-one prints usage on the first real run). tools/spec scripts use top-level sibling imports (`from check_capabilities import ...`) which work only in script mode (script dir = sys.path[0]); pytest VER tests load them via `tests/meta/_tools.py::load_tool` (importlib, module name `tools_spec_<name>` to avoid clashing with task-1's registered "extract_requirements"). Deps for tools (PyYAML/jsonschema) + pydantic live in `apps/api/pyproject.toml` — the root pyproject is virtual (`package = false`) and fenced; the shared `.venv` makes them importable from tools.

5. **ruff gate shape**: tools get D/ANN enforced (every `__init__` needs a one-line docstring for D107, private fns need return annotations ANN202), tests ignore D/S/PLC0415/N999. Complexity ceilings bite on gate scripts: C901=10 and PLR0912=12 — split per-item checks into `_check_<unit>` helpers returning `list[Finding]` and compose with `findings.extend(...)`; also PLR2004 (magic numbers → named constants with the normative origin in a comment), PT018 (split compound asserts), PERF401 (comprehension/generator over append loops).
