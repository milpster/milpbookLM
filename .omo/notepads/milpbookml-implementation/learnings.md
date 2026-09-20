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

---

## FND-03 (2026-09-19)

1. **`GRANT … ON DATABASE current_database()` is INVALID SQL**: GRANT takes a literal object name, not an expression — `current_database()` inside a GRANT is a syntax error (caught only when the smoke ran roles.sql with `ON_ERROR_STOP=1`; plain `psql -f` continues past the error and hides it). The DB-agnostic pattern that works: issue the DATABASE-level grants from a DO block via dynamic SQL — `EXECUTE format('GRANT ALL ON DATABASE %I TO milpbooklm_migration', current_database());` — while schema-level grants (`GRANT … ON SCHEMA public`) stay plain statements (the schema name is constant per DB). Keep the comment explaining WHY the indirection exists, or a future cleanup reverts it to the broken form.

2. **Immutable tables make test-harness cleanup impossible as the app role**: the 9 fully-immutable tables (BEFORE UPDATE OR DELETE → RAISE) mean a harness that cleans up by NULL-ing FKs (UPDATE) or deleting rows (DELETE) is blocked by the invariants it just verified — that is the invariants WORKING, not the schema being broken. 13/20 invariants tests failed exactly this way in cleanup after their body assertions passed. The wave-2 fix: run cleanup over a SUPERUSER connection with `ALTER TABLE <t> DISABLE TRIGGER USER` on the 9 tables → LIFO deletes (children before parents, since FK cascades fire row triggers too) → re-enable. Never put DB drops in a per-test fixture (3 conftests each run ensure_pg → 3x per session).

3. **/run/user is tmpfs — a host reboot silently wipes the whole direct-binary PG setup** (rootfs, hostlibs, pgdata, all of it) while the repo on disk survives. Rebuild recipe (all in /tmp/opencode/fnd03-scratch/): `rebuild-scratch.sh` (pull the 15 OCI layers of digest sha256:1d50c689… via auth.docker.io token API, extract usr/lib/postgresql* + usr/share/postgresql*), `fetch-deb-libs.sh` (bookworm .debs for libicu72/libldap-2.5-0/liburing2 — liblber-2.5.so.0 ships INSIDE libldap-2.5-0, there is no standalone bookworm liblber package), `bringup2.sh` (initdb + pg_ctl on 29517). Also: the rootfs `psql` does NOT work (needs the image's libpq.so.5, which we don't ship in LD_LIBRARY_PATH) — use the host psql (a PG17 client talks to a PG18 server fine) for ad-hoc SQL.

4. **One-time state transitions interact with FK-nulling cleanup**: the fixed `milpbooklm_evidence_snapshot_guard` (one-time promotion: once `promoted_source_version_id IS NOT NULL`, any change RAISEs) correctly blocks a cleanup that tries to `SET promoted_source_version_id = NULL` before deleting the referenced source version. Design rule for such guards: they make the promoted row unlinkable except via DELETE of the row itself — the table must stay deletable (no immutability trigger) or cleanup must go through the privileged path. Probe evidence: .omo/evidence/task-3-migration-smoke.log + the 7/13 probe split in .omo/evidence/task-3-milpbookml-implementation.json.

---

## FND-04 (2026-09-19)

1. **The inherited "3 QA failures" were all defects of the LOST driver, not the code** — the rebuilt driver (same 40 checks) is 100% green with zero code changes. Root causes: (a/b) the lost driver re-sent a REVOKED token after the owner re-login (401 "authentication required" is the CORRECT answer); (c) its rate-limit probe reused an email whose `login:<ip>:<email>` limiter key already held one attempt from the disabled-owner login check (the 429-on-the-6th is exactly the configured `login_max_attempts=5` behavior). Lesson: before "fixing" a dead worker's failing QA, reproduce with a clean driver — the failure may live in the harness.

2. **Limiter keys are per-IP-per-email and count EVERY attempt (successes too)** — a QA flow that logs the same account in more than 5 times in 15 min (or registers more than 3 accounts per IP/hour, the configured register default) gets uniform 429s. QA recipes: rate-limit probes need a FRESH account (seed it via SQL with a real argon2id hash — the check exercises its LOGIN key, not registration), and multi-account flows should clear the cookie jar between users so the register budget and the CSRF middleware don't entangle with the check under test.

3. **CSRF middleware intercepts EVERY unsafe /api/v1 request carrying a live session cookie — including POST /login** (the middleware runs before the route). So an authn probe like "disabled owner cannot log in" must run with an EMPTY cookie jar, or it gets 403 csrf_rejected before authn runs. Also: session cookies are Secure, so TestClient needs an https base_url (unit tests use `https://testserver`) or the jar silently drops them.

4. **QA PG after the /tmp wipe: host PG17 + a 4-line uuidv7() SQL shim is enough** — the only PG18-specific element in the FND-03 baseline DDL is the `uuidv7()` PK default; a scratch-only shim (48-bit unix-ms timestamp | version 7 | variant 10 | random) makes the whole baseline migrate on the host PostgreSQL 17 + pgvector 0.8.2 (~110ms, port 29518). Keep the shim OUT of the repo. Also: `make_engine()` picks the DBAPI from the DSN scheme — `postgresql://` means psycopg2 (NOT installed); the engine DSN must be `postgresql+psycopg://` while psycopg3-direct (harness/driver fixtures) accepts the plain scheme.

---

## FND-05 (2026-09-20)

1. **Starlette route registration order is load-bearing with typed path params**: a static segment registered AFTER `/{job_id}` (uuid.UUID) is shadowed — the `[^/]+` pattern matches "events" first, UUID validation 422s, and Starlette never falls through to the later `/events` route (silent, no warning). Register static paths before parameterized ones (job_routes.py: /events before /{job_id}).

2. **Read the T3 CheckConstraints BEFORE writing terminal transitions**: `ck_jobs_lease_consistency` (`lease_owner IS NULL OR status IN ('leased','running')`) made complete()/cancel() crash on the first happy-path publish — the recovery path had the lease NULL-clears, the happy path didn't. Related: `idempotency_keys.expires_at` is NOT NULL with NO server default — `pg_insert(...).values()` only sets what you pass, and a defined-but-unused TTL constant (`_IDEMPOTENCY_TTL_SECONDS`) is a bug magnet.

3. **rtk + background processes gotchas**: `cmd > file 2>&1 &` through rtk loses the redirection (the process runs, logs stay empty forever); route background boots through a script file (`setsid bash start.sh > log`) whose contents rtk does not rewrite. And `pkill -f "pattern"` self-matches the invoking `bash -c` line — use the bracket trick (`milpbooklm_[a]pi`) so the pattern string in your own cmdline doesn't match; a single missing character in the pattern (an underscore!) silently kills nothing, and the next bind then fails with EADDRINUSE while the stale server serves the old code.

4. **Worker kill for lease-recovery QA**: SIGKILL of the process-group head (the rtk/uv wrapper) orphans the real python child (rtk -> uv -> python3); `pgrep -f` on a CLI arg (`--worker-id w1`) catches all three tiers at once. In a recovery scenario ANY other live worker can be the one that recovers (in the actual run, the surviving w1 — not the freshly spawned w2b — took the job), so assertions must be owner-agnostic: check attempt rows for "[killed owner: running] [other owner: succeeded]", not a specific worker id.

---

## FND-06 (2026-09-20)

1. **`initdb --no-locale` silently produces an SQL_ASCII server, which makes psycopg3 return text columns as `bytes`** — SQLAlchemy 2.0.54 then crashes in its dialect initialize with `TypeError: cannot use a string pattern on a bytes-like object` (`_get_server_version_info` regex-matches `select pg_catalog.version()`). The symptom masquerades as a SQLAlchemy/psycopg incompatibility; the cure is `initdb --encoding=UTF8 --locale=C` (locale C + UTF8 is a valid combo). Every scratch cluster for this repo must be UTF8.

2. **`ck_blob_objects_finalized_timestamp` is load-bearing for GC**: it is `(state = 'finalized') = (finalized_at IS NOT NULL)`, so moving a row to `purged` while keeping `finalized_at` set VIOLATES it. `mark_purged` must set `state='purged'` and `finalized_at=NULL` in the same UPDATE (FND-05 lesson 2 again: read the CheckConstraints before writing the transition).

3. **`os.link` is the atomic no-overwrite finalize; `os.rename` is not allowed here** — rename silently replaces an existing target, which would mutate a finalized blob. link() is atomic on POSIX and raises EEXIST when the target exists; the race-winner path is safe by content addressing (verify the existing object's digest+size, then dedupe). Directory fsync (open O_RDONLY|O_DIRECTORY + fsync) is required after the link for durability.

4. **The put protocol has no staging-row-first two phase**: `blob_objects.storage_path` is NOT NULL and digest-derived, so the row cannot exist before the write. The guide's ordering is followed exactly (temp -> validate -> fsync -> link -> dir fsync -> ONE-transaction object+reference commit); a crash between finalize and commit leaves a complete self-verifying file with no record (an unreferenced final), which GC handles after the safety delay. `commit_finalized` reuses an existing row for the same digest and completes a stale `staging` row (re-finalize) in that case.

5. **Worker maintenance CLI = the durable blob maintenance path without API surface**: `python -m milpbooklm_workers --command {reconcile,put-blob,get-blob,gc}` reuses the same `BlobPorts` wiring as the loop's `blob.integrity_scan` job kind (registered only when `--blob-root` is set). Reuse of a variable name with a different type in one function (`report = ports.reconcile()` ... `report = ports.gc()`) is a mypy `[assignment]` error — name the second one `gc_report`.

6. **Smoke DSN gotcha re-hit**: `make_engine("postgresql://...")` selects psycopg2 (not installed) — engine DSNs must be `postgresql+psycopg://` (FND-04 lesson 4). Also, bare uuid literals in psql (`66666666-7777-...`) parse as arithmetic; quote + `::uuid`.

7. **The FND-03 finalize-guard trigger makes `finalized` TERMINAL — no code may UPDATE a finalized `blob_objects` row, not even to `purged`** (takeover finding). `trg_blob_objects_finalize_guard` (declared in `db/triggers.py`, applied by the FND-03 baseline) raises on any UPDATE with `OLD.state='finalized' AND NEW.state <> 'finalized'` — the RAISE message says "may only be purged", but the logic blocks purged too; the logic is the law. Consequences: (a) SQLAlchemy `Table` metadata shows ZERO triggers — reading `tables/blobs.py` alone is not enough, read `db/triggers.py` before writing any state transition (FND-05 lesson 2 extended); (b) the abandoned T6 `mark_purged` crashed the first GC over a record-based unreferenced final — and its smoke missed this because its aged final was FILE-ONLY (no row → mark_purged never called); (c) T6's GC therefore deletes files only, and a finalized record whose file is gone is a permanent bookkeeping remainder (reported as unreferenced_final with `file_present=False`, settled/skipped by GC, never re-mutated). The `purged` state is reachable only via INSERT (the trigger is BEFORE UPDATE) — owned by a future privileged purge path, not by GC.

8. **GC over record-only findings needs an explicit file-present discriminator**: a record whose object file is already absent has no bucket dir (`objects/<aa>/`), so `delete_final` must guard the directory fsync (`path.parent.is_dir()`) — an unconditional `os.open(O_DIRECTORY)` raises `FileNotFoundError` mid-GC. The discriminator lives on the finding itself (`ReconciliationFinding.file_present`) set by the classifier that knows which artifact space (disk listing vs DB rows) produced it — not re-derived from detail strings.
