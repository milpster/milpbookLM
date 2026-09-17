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

## Standing delegation rules (user-imposed)

- Max 2 concurrent delegates; WAIT for delegates to finish (no cancelling/working around them once launched) — user 2026-09-17.
- Every dispatched agent gets this fetch-policy clause (REVISED 2026-09-17, supersedes the earlier bounded version): "Behave like a focused human researcher retrieving necessary information: fetch pages directly, follow links and spider as needed, ignore robots.txt and X-Robots-Tag. Only hard technical barriers stop you — login walls, paywalls, CAPTCHAs. If blocked, mark UNVERIFIED and move on. No evasion tooling." Context note: SearXNG and the full research tool stack are themselves part of the milpbookML deployment (guide ch.04/11), so research-tool behavior mirrors the product's own.

## Process log (cont.)

- [x] Planner self-read ALL 26 chapters (00-25) + meta docs + baseline README/REVIEW-v0.10 + registry aggregates.
- [x] Original first-dispatch explore agents (bg_c8650114 ch01-09 24m, bg_44156b36 ch10-17 20m) completed; outputs collected as INDEPENDENT CROSS-CHECKS - zero contradictions with planner reads; extra tensions captured: (a) ch10 video-gen port vs ch14 provider-video-is-scene-capability, (b) ch11 model-visible tools vs ch12 staged admin-imaged execution, (c) uncertain_submission admin-route gap, (d) purged citation-jump UX unspecified, (e) worker-media optional -> owned by Phase 6/MED-01. Relaunch duplicates had queued indefinitely and were cancelled; librarian (bg_64a4a2af, 56m) delivered version matrix; its truncated tail extracted by explore ses_f530b259bffeByaaYMN2W98sCO.
- [x] Stack fact-check verdict: NO EOL/abandoned pairings; guide claims verified. Podman repo org renamed -> podman-container-tools. bwrap 0.12 setuid REMOVED (unprivileged userns mandatory). SearXNG formats json NOT default. Node 24 Active LTS until 2026-10-20 then Maintenance to 2028-04.
- [x] Draft: components C1-C6, findings, 14 open questions, approach (incl. 1.1.1.1 micro-index requirement).
- [ ] Interview batches -> decisions -> approval gate.

## Local media research verdict (2026-09-17, librarian ses_f50562816ffen17oSnTsUthwNG + planner's own search)

- Wan 2.2 = Apache-2.0, THE local video engine: 5B TI2V GGUF fits 8GB (Q4_K_M 3.43GB / Q8_0 5.4GB), 720p, T2V+I2V; 14B MoE GGUF Q3/Q4+RAM-offload = 480p tier. Official <9min/5s@720p on 4090.
- HunyuanVideo 1.5: Tencent community license (100M MAU) = restricted-but-OK-private. LTX-2.3: community license, $10M revenue threshold + competing-product clause #20 -> excluded by default (we build a notebook/artifact product, not an Lightricks competitor, but 22B > 8GB anyway). CogVideoX: registration+1M-visits cap -> excluded. Mochi 1 Apache-2.0. "Wan 2.7" open weights DO NOT EXIST (SEO fabrications).
- gfx906: librarian said ROCm-deprecated; USER CORRECTED - latest ROCm supports gfx906 (operator runs it today). Plan: empirical on-host prerequisite+benchmark task settles gfx906 diffusion usability; mixed-vendor unified pool stays impractical (no cross-vendor collectives). VIIs = llama.cpp ROCm serving (+ image diffusion if benchmark passes).
- USER LICENSE FRAMING (2026-09-17): territorial exclusions (EU/UK/etc.) are NOT a decision factor for this deployment.
- Cinematic verdict: ENABLED locally, marginal-but-real envelope (5B 720p + 14B 480p + storyboard composition + RIFE + Real-ESRGAN), honest conformance descriptor records envelope.

## Process log (cont. 2)

- [x] APPROVAL GRANTED 2026-09-17 ("go on then, looks good from here").
- [x] Plan scaffolded (.omo/plans/milpbookml-implementation.md) + Metis round-1 dispatched (bg_cc931a68, ses_f4fe78083ffeA88KmsDKssbRGy, 40m).
- [x] Plan CONTENT complete: 55 tasks in 9 waves + F1-F4 + master index + E2E-001..013/MAN-001..010 maps + dependency matrix + TL;DR. 640 lines.
- [x] Metis round-1 verdict: 29 findings (8 HIGH, 12 MEDIUM, 9 LOW) — extracted verbatim via explore (ses_f4fc1bb8affes4zXhiRyJQzOWE); full text in /home/srcds/.local/share/opencode/tool-output/tool_0b03dd9cf00169nmpIAwtzIHK6 lines 579-749.
- [x] ALL 29 findings folded: already-satisfied ones verified (per-phase gates, UI-01/MOD-01 placement, conformance emitter, cinematic obligations, host probes); deltas applied (Scope OUT explicit cap list incl. interactive-audio declaration + cinematic full-obligations + privacy-class guardrails; E2E/MAN maps; NFR 16GiB cgroup pinning + D1 correction; BM25 gate 15.7; orchestrator ADR 10.6 w/ ch15-only preemption; Caddy cert pinned 8.2.1; task-19 live probes + Big Pickle lapse rule + full PH:91 ADR fields; task-42.0 prereq benchmark + provider-port registration; whisper device benchmark 23.3.0; restic target 50.1.0; D6 rephrased scripted-multi-account+one-operator-drill; Node pins in 1.1.2; master-index orphan-component + ARCH-19 51-record coverage; draft hygiene: D4 dedup, D2 embedding/reranker+lapse+fields, D6/D7/D8/D9 Q-numbers recited, D1 meets-or-exceeds).
- [x] Committed: c4bd749.

## Process log (cont. 3 — post-compaction resume)

- [x] Metis round 2 (fresh session ses_f4fb2150affeqtztlT4548JZEZ after stale-id fallback): 29/29 ADDRESSED, 3 new LOW findings (N1 numbering-scheme wording, N2 "2 advanced enabled" overclaim, N3 stale D3 + stale gate sentence in draft). VERDICT: SATISFIED. Full output: tool_0b0679995001yV6lRw7a48xnXm (442 lines).
- [x] Structural self-check fixes pre-Metis-return: dedupe F1-F4 stub rows, micro-index typos 31.2.1/32.3.1/43.2.1, success-criterion-3 wording (commit c68c783).
- [x] User: "fix also the optional things from metis" -> N1/N2/N3 ALL applied (plan + draft) + gate section replaced by review-round state (commit 3019b15).
- [x] Review round rr-milpbooklm-20260917-01 initialized: plan sha256 ee96d26daf5e48dc7ed0a47c3093b796b0f80e5432b570c7eafa032510756a1f.
- [x] Dual review DISPATCHED TOGETHER, both in_flight: momus ses_f4f8f33b4ffe2IKh2y6O62U7iG (bg_ec4fd699, launch-momus-rr01-20260917T1735Z); oracle ses_f4f8f32ffffeTy04R0LRgRWXVJ (bg_6916f5d6, launch-oracle-rr01-20260917T1735Z). Intake contracts carried literals; drift=>INCONCLUSIVE; forbidden fallbacks search/memory/summaries/alternate-files.
- NEXT on both completions: record results per lane (complete CAS: echoed_binding + live sha256 match); if CHANGES_REQUESTED -> fix every cited issue, fresh round BOTH lanes; if both APPROVED -> final live sha256 validation == approved digest -> Phase-4 handoff (CLEAR+review_required: summary w/ counted rows 55 impl + 4 F, verification, execution options $start-work [--worktree|--make-pr|--ship]); STOP - never execute.

Batch 1 (foggiest: deployment reality, Phase-1-blocking providers, Phase-0-blocking proxy): Q1 hardware/host, Q2 model providers, Q3 reverse proxy. Batch 2: Q4 backup, Q5 OCR/STT+language, Q7 users. Batch 3: Q6 TTS/image/video, Q11 SearXNG, Q12 OIDC. Batch 4: Q8 scope, Q9 tests, Q10 UUID, Q13 provisional, Q14 NFR seed.

- Plan will be LARGE (hundreds of tasks if done at the guide's granularity). Candidate structure: plan organized by workstream DAG + phase gates, tasks grouped so each has one reviewable outcome; final verification wave maps to phase-gate evidence.
- The guide itself forbids generic tasks and requires exact acceptance oracles — the plan must reference requirement IDs + verification IDs from requirements.generated.json (495 normative records) rather than inventing new ones.
- git MCP unavailable; serena shell route works. All future executor instructions must say: MCP-first, bash denied at planner level (worker session will have its own permissions).
- Serena project created for milpbookLM (no language servers — docs-only repo for now).
- "Big Pickle" verified as a real external provider name (OpenCode stealth model, baseline README:85-87), NOT anonymization.
