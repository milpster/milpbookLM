# Planning Journal — milpbookML implementation plan

Session: 2026-09-17, Prometheus (ulw-plan), intent=CLEAR (user asked to be interviewed: "ask everything that is unclear"), review_required=true ("make sure everything is accurately actionable and will result in the desired output"). Classification: ARCHITECTURE-scale.

## Working rules (user-imposed)

- Read ALL enclosed documents chapter by chapter; skip nothing.
- Translate into ONE actionable plan per the guide's own PLANNING-HANDOFF.md planning-output contract.
- Ask every surviving fork; user claims the decisions.
- Journal every step; use git; MCP tools before bash (bash is permission-DENIED for this agent — serena_execute_shell_command is the shell route; git MCP not connected in this session).
- Delegate as much as possible; max 2 agents at a time.

## Facts established so far

- Package: milpbookML technical implementation guide v1.2 FINAL (2026-09-16), embedding architecture v0.10 FINAL. Self-hosted multi-user source-grounded research notebook (Gemini Notebook task-equivalence, no Google deps).
- Stack frozen by TAD-001..012: Python 3.13/uv/FastAPI/Pydantic v2/SQLAlchemy 2/Alembic/psycopg 3; Node 24 LTS/pnpm/React 19/TS/Vite/TanStack; PostgreSQL 18 + pgvector (only mandatory data service); PG-backed jobs/leases/outbox; rootless podman compose (pinned podman-compose); SearXNG; Playwright; Bubblewrap+cgroupv2; pytest/Hypothesis/Vitest/Playwright Test/axe-core.
- Requirement ID scheme: ARCH-CC-NNN / TECH-CC-NNN; CI fails on unclassified MUST/SHOULD occurrences (tools/spec/extract_requirements.py).
- Authority order (PLANNING-HANDOFF): architecture baseline 00+chapters > technical chapters > capabilities.generated.json > requirements.generated.json > handoff sequencing. Contradiction = spec defect, blocks task, never silently resolved.
- Planning output contract: epics -> work packages -> tasks; each task needs ID, workstream, capability/requirement IDs, deliverables+paths, prereqs/dependants, data/schema/API/event changes+migrations/rollback, authz/privacy/idempotency/failure, fixtures+positive/denial/failure/recovery tests, acceptance oracle+evidence path, execution tier+phase gate, blocking decisions. No generic tasks ("implement backend" banned). No claiming code exists because spec defines it.
- 21 workstreams (FND-01..07, MOD-01, ING-01/02, IDX-01, RAG-01, UI-01, RSR-01, EXE-01, STD-01..03, MED-01, COL-01, OPS-01, SCOPE-GUARD). Critical path: FND-01 -> FND-03 -> FND-05/FND-06 -> ING-01 -> IDX-01 -> RAG-01 -> STD-01.
- Phases 0..7 with entry/exit gates; no phase exits with placeholder adapters, unclassified requirements, unexplained SHOULD deviations, failed mandatory tests, stale evidence.
- Bounded decisions with deadlines (PLANNING-HANDOFF "Decision deadlines"): local text-gen+embedding reference providers (before Phase 1 acceptance); reverse proxy/TLS terminator (before Phase 0 production-equivalent evidence); backup/snapshot utility+key recovery (before first RC); OCR/STT engines+language profile (before affected Phase 2 tasks); TTS/image/video providers+modes (before affected Phase 6 tasks); BM25-vs-alternative lexical ranker (only after PG FTS evaluation shows material benefit; never blocks baseline).
- Scope: 61 capabilities; 507 requirement occurrences (495 normative, 12 definitional); 364 architecture headings mapped; 13 canonical E2E journeys; 10 manual scenarios. Non-targets: Kubernetes, Kafka, Redis, ES/OpenSearch, standalone vector DB, MinIO, knowledge graph, plugin marketplace/SDK, native mobile, PWA/offline, SaaS tenancy, Google integration, pixel-perfect cloning. BrowserOS explicitly NOT a dependency.
- Zip = copy of extracted docs (user confirmed 2026-09-17); no separate verification needed.

## Process log

- [x] Loaded ulw-plan skill + intent-clear + full-workflow references.
- [x] Read meta docs: README, PLANNING-HANDOFF, 00-status-decisions, PARITY-SCOPE-AUDIT, REFERENCE-DEPENDENCIES, CHANGELOG, REVIEW-FINAL, AUDIT-v1.0.
- [x] git init -b main; initial commit ba9f31b (guide as received, 71 files).
- [x] Scaffolded draft .omo/drafts/milpbookml-implementation.md (--clear --draft-only --review-required).
- [~] Delegated (2 concurrent, background): explore ch.01-09 (bg_f13d2ad1 / ses_f53522334ffero0lOqCm3DZk4a), explore ch.10-17 (bg_c1277c2f). First dispatch attempt died (env issue), relaunched on user go-ahead.
- [ ] Self-read of fork-deciding chapters (01, 02, 22, 23) — in progress next.
- [ ] Wave 2 delegates: ch.18-25 + registries/baseline/schemas; librarian external fact-checks.

## Open questions queue (for the interview; grow as chapters are read)

(owner-decisions per guide's own decision deadlines + environment forks; ask WITH why, options, recommended default)

1. Target hardware/envelope for this host (GPU? RAM? cores?) — gates model provider selections.
2. Local text-generation + embedding reference providers (deadline: before Phase 1 acceptance).
3. Reverse proxy / TLS terminator + certificate procedure (deadline: before Phase 0 production-equivalent deployment evidence).
4. Backup/snapshot utility + key-recovery procedure (deadline: before first RC).
5. OCR/STT engines + language profile (before Phase 2 tasks affected).
6. TTS/image/video providers + supported modes (before Phase 6).
7. Single-user vs multi-user deployment reality for v1 acceptance (spec is multi-user; acceptance "production-equivalent" — confirm operator context).
8. Phase scope of THIS plan: all phases 0-7 in one plan (guide demands "every applicable capability assigned exactly once") vs phased delivery gates.

## Registry statistics (computed from generated JSON, 2026-09-17)

- Capabilities 61: stable/core 44, late/optional 7, provisional/announced 4, advanced/provider-dependent 2, deliberate-non-target 4. By phase: P1=15, P2=13, P3=4, P4=8, P5=2, P6=4, P7=11, no-phase=4. By workstream: ING-02=14, STD-02=9, MED-01=6, RAG-01=6, COL-01=5, UI-01=4, SCOPE-GUARD=4, ING-01=4, RSR-01=3, STD-01=2, STD-03=2, EXE-01=1, MOD-01=1 (FND/OPS workstreams own no capabilities — pure infrastructure).
- Requirements 507 total: must 264, must_not 78, should 142, should_not 11, narrative 12 → 495 normative, 342 hard (must/must_not). By chapter: ch00=53, ch04=22, ch05=21, ch06=20, ch09=18, ch10=29, ch12=18, ch15=27, ch17=33, ch19=51, ch21=47, ch25=52 (heavytails).
- Verification tiers: pull_request 155, nightly 166, release_candidate 170, review 4, none 12. Levels: meta 108, security 102, e2e 79, performance_manual 47, integration 35, contract 33, fault 27, property 21, golden 10, evaluation 9, automated_manual 16, analysis 4, architecture 4.
- Every requirement record carries: verification_ids (VER-*), test_path, fixture, oracle, execution_tier, evidence_path (artifacts/verification/VER-*.json), result=not_run. The PLAN must reference these, not invent new oracles.

## Architecture baseline highlights (baseline README + REVIEW-v0.10)

- Central rule: no model vendor/embedding/search/media/connector/storage backend may enter the notebook domain model.
- "OpenCode Big Pickle" = free limited-time external OpenAI-compatible stealth model; treated as replaceable external/bootstrap/fallback candidate, NEVER trusted/local default, not a dependency. Data-use caveat noted.
- Ordinary chat = tool-free, notebook-grounded; explicit selected notes are version-pinned prompt context. Agentic Chat = separate tool-capable path.
- Local accounts auth baseline; OIDC/trusted-proxy optional. Account disablement immediate; sole-owner notebooks → locked admin custody. Deletion: removal vs hard purge; purge traverses all derivatives; backups expire under finite retention.
- AD-011: external-provider default policy + disclosure; AD-012: execution networking (no network by default); AD-023: derived-content restriction propagation; AD-024: crash-consistent blob lifecycle; AD-026: capability applicability/conformance profile.

## Insights / risks

- Plan will be LARGE (hundreds of tasks if done at the guide's granularity). Candidate structure: plan organized by workstream DAG + phase gates, tasks grouped so each has one reviewable outcome; final verification wave maps to phase-gate evidence.
- The guide itself forbids generic tasks and requires exact acceptance oracles — the plan must reference requirement IDs + verification IDs from requirements.generated.json (495 normative records) rather than inventing new ones.
- git MCP unavailable; serena shell route works. All future executor instructions must say: MCP-first, bash denied at planner level (worker session will have its own permissions).
- Serena project created for milpbookLM (no language servers — docs-only repo for now).
