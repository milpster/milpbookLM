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
- [x] Scaffolded draft .omo/drafts/milpbooklm-implementation.md (--clear --draft-only --review-required).
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
- [x] Plan scaffolded (.omo/plans/milpbooklm-implementation.md) + Metis round-1 dispatched (bg_cc931a68, ses_f4fe78083ffeA88KmsDKssbRGy, 40m).
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

## Process log (cont. 4 — rr-02 results + fixes + rr-03)

- [x] rr-02 BOTH LANES COMPLETED with echoed binding + digest match: momus = CHANGES_REQUESTED (4 defects: E2E-006/007 swap lines 34/424/439; MAN map mislabels 6/10 spec ids line 35+600; matrix row 53 missing dep 54; workstream count 21->22). oracle = CHANGES_REQUESTED (7 defects: missing edge 41->40; media_generation orphaned from F1; "exactly once" contradicts distribution + 9 unnamed subset splits; Blocks column mixed direct/transitive; MAN-007 owner wrong; digest stale vs canonical JSON on ARCH-05-001/ARCH-14-001/ARCH-01-002..004; minors: zero-human header carve-out, deployment double-count, SSRD typo). Results + transcripts recorded (commit 7637356).
- [x] ALL 11 defects FIXED (commit 0f811ae): E2E 006/007 swapped to spec order (lines 34/424/439 + task 24/35 acceptance consistency); MAN map fully relabeled to spec names w/ corrected owners (MAN-001->17/20, MAN-004/005 un-swapped, MAN-006->10/17/19, MAN-007->5/49/51, MAN-008->50) + task 54 list rewritten + browser-compat/install legs marked plan-internal; matrix row 41 deps 23,31,40 + row 53 deps 49..52,54; ENTIRE Blocks column rebuilt as direct dependants + authority note; task 40 References now cite ARCH-14-001..016 + Table A row media_generation; line 21 "22 workstreams" + exactly-one-owner-except-declared-shared wording; master index: canonical-label rule (JSON labels govern; canonical totals platform_core 61/deployment 22/domain_model 21/capability_registry 9/media_generation 16/studio_artifacts 15) + declared shared set + per-component subset splits; verification header carve-out for MAN human sign-off; deployment(23 incl. ARCH-05-001); SSRF typo; digest got CANONICAL-LABEL CORRECTION note. Plan sha256 ee96d26d -> 484036d5 (638 lines).
- [x] rr-03 DISPATCHED fresh (both lanes, plan 484036d5): momus ses_f4efbad6cffe8Y69kF0KJrXCq (bg_071edcf8, launch-momus-rr03-20260917T2016Z); oracle ses_f4efbad5effercuHEjkJehc5kW (bg_d58baa97, launch-oracle-rr03-20260917T2016Z). Receipts recorded in draft.
- NEXT: on rr-03 verdicts -> if both APPROVED: final live sha256 == 484036d5 -> Phase-4 handoff; else fix + rr-04. STANDING: never cancel lanes on elapsed time; wait for system notifications.

## Process log (cont. 5 — rr-03 verdicts + USER HALT)

- [x] rr-03 BOTH LANES COMPLETED (echoed binding + digest 484036d5 verified): momus = CHANGES_REQUESTED (3 defects: phantom TECH-01-001/002 IDs in tasks 1/17; ~25 stale Blocks fields violating L118 direct-dependants rule — my rr-02 fix rebuilt the MATRIX but not the per-task row Blocks; L57 ARCH-05-001 owner self-contradiction). oracle = CHANGES_REQUESTED (6 defects: same Blocks staleness; matrix rows 26/33/34 gate omissions; success-criterion-3 contradicts cinematic downgrade path; wave-8 "OPS-01b..f" phantom label; stale "task 29/39" refs; Caddy unpinned). KEY: authoritative Depends/Blocked-by side verified 100% consistent by BOTH lanes — no ordering hazard; remaining issues are traceability/labeling. Oracle remediation estimate: <1h mechanical.
- [x] USER HALT: "stop before running the high accuracy reviews" -> NO rr-04 dispatched. Results + union fix list recorded in draft; committed.
- RESUME POINT: (1) apply union fix list (draft carries it verbatim): remap TECH-01 refs, regenerate ALL Blocks fields (55 task rows + matrix, consistent gate convention), align L57 first clause, downgrade-aware success criterion 3, wave-8 label fix, drop "/39", pin Caddy v2; (2) re-hash plan, init rr-04, dispatch BOTH lanes fresh; (3) on both APPROVED -> final live sha256 validation -> Phase-4 handoff. Plan sha256 at halt: 484036d5, tree clean.

## Process log (cont. 6 — resume: union fixes applied + rr-04 dispatched)

- [x] User: "go on" -> resume executed in full. Union fixes applied (commit 71af9a7): TECH-01-001 dropped from task 1 (refs+commit); TECH-01-002 in task 17 replaced by ch01-chapter-obligation notes + explicit ARCH-09-*/TECH-09-001 mapping (What/MustNOT, References, Commit); ALL Blocks fields REGENERATED by script (/tmp/fixblocks.py: parsed authoritative Blocked-by incl. range expansion, computed direct dependants, rewrote 48 task-row Blocks + 27 matrix cells, gates annotated " (gate)", F-targets 53/55 preserved; spot-verified rows 1/2/8/9/26/31/33/41/48; "all gates" gone); L57 anomalies clause now "ARCH-05-001->task 8 (owner - see shared-set entry below)"; success criterion 3 downgrade-aware (cinematic ENABLED-with-envelope OR disabled-with-recorded-evidence both satisfy); wave-8 label "OPS-01b..e = tasks 49-52 + release audit 53, manual runbooks 54, docs/ADR index 55; 7 tasks"; both "task 29/39" refs -> "task 29"; Caddy pinned "v2 (major pinned here - exact minor + image digest pinned under task-1 lock discipline)". Verified: TECH-01 count 0, 29/39 count 0. Plan sha256 484036d5 -> 3615e1cd (638 lines).
- [x] rr-04 DISPATCHED fresh (plan 3615e1cd): momus ses_f4e881bfcffep5FVdQfCETB09Z (bg_16165530, launch-momus-rr04-20260917T2222Z); oracle ses_f4e881af2ffe0XtiMKcba0ntKF (bg_0008ffbe, launch-oracle-rr04-20260917T2222Z). Receipts recorded in draft; committed.
- NEXT: on rr-04 verdicts -> both APPROVED: final live sha256 == 3615e1cd -> Phase-4 handoff (CLEAR+review_required: summary w/ counted rows 55 impl + 4 F, review receipts, execution options $start-work [--worktree|--make-pr|--ship]); else fix + rr-05. STANDING: never cancel lanes on elapsed time; wait for system notifications; git-commit every state change.

## Process log (cont. 7 — rr-04 close-out, rr-05 final: BOTH LANES APPROVED, LOOP COMPLETE)

- [x] rr-04 verdicts (digest 3615e1cd): momus = VERDICT-APPROVED, ZERO defects; oracle = CHANGES-REQUESTED on exactly ONE minor citation defect (L335 task-24 refs pointed AD-015/016 at "baseline README" — definitions live in architecture-baseline/00-status-decisions.md ~L76/80). Oracle also CLEARED META-REQ-001 (legitimate ch25 test-group id) and verified ~30 requirement ranges with zero phantoms. Fix applied (L335 repointed), rr-05 initialized on digest 5ba76bc0, both lanes dispatched FRESH (commits 2b41ec2, ef24f24).
- [x] Context compacted twice mid-round; handoff documents preserved state; serena re-activated post-restart.
- [x] rr-05 verdicts (digest 5ba76bc0): momus = VERDICT-APPROVED, ZERO defects (rr-04→05 delta verified on disk; L76/L80 exact). oracle = CHANGES-REQUESTED citing ONE defect — but the defect QUOTED a string ("E2E-006→24/4") that exists NOWHERE in the artifact: planner byte-verified L34 actually reads "E2E-006→14/24" (only "24/4" on L34 belongs to the adjacent, correct E2E-010 entry; L336 "w/ task 14" consistent; ascending-order map convention). LESSON: reviewer defect citations are CLAIMS too — byte-verify against the artifact before acting.
- [x] Disposition: NO cosmetic edit (would validate a false premise AND invalidate momus's valid approval of the digest). Oracle lane CONTINUED IN-SESSION (same session/launch/round, artifact frozen+re-verified) with the byte evidence; oracle re-ran fixed-string counts itself, RETRACTED the defect in full ("the planner is correct; I misquoted" — transposition of adjacent token), and RESTATED: VERDICT-APPROVED, unconditional, with receipt (commit 4da7ff8 records the challenge state).
- [x] FINAL VALIDATION (post-verdict): live sha256 == 5ba76bc0d8ed656ad0fcb15afba45429a874c714e6e9dcabaafeb0e8340612e5 ✓; counted rows: 55 `- [ ] N.` implementation + 4 `- [ ] F<n>.` final ✓; 638 lines ✓). Completion CAS satisfied for rr-milpbooklm-20260917-05: both lanes APPROVED on the SAME digest.
- [x] REVIEW LOOP COMPLETE: rr-01 inconclusive (infra) → rr-02 both CHANGES (11 defects fixed) → rr-03 both CHANGES (union fixed incl. scripted Blocks regeneration) → rr-04 momus APPROVED + oracle 1 citation fix → rr-05 BOTH APPROVED. Metis SATISFIED before the loop. Plan APPROVED FOR HANDOFF.
- NEXT: Phase-4 handoff presented (plan summary w/ counted rows, review receipts, execution options $start-work milpbooklm-implementation [--worktree <path>|--make-pr|--ship]); planner STOPS — never executes.



- Plan will be LARGE (hundreds of tasks if done at the guide's granularity). Candidate structure: plan organized by workstream DAG + phase gates, tasks grouped so each has one reviewable outcome; final verification wave maps to phase-gate evidence.
- The guide itself forbids generic tasks and requires exact acceptance oracles — the plan must reference requirement IDs + verification IDs from requirements.generated.json (495 normative records) rather than inventing new ones.
- git MCP unavailable; serena shell route works. All future executor instructions must say: MCP-first, bash denied at planner level (worker session will have its own permissions).
- Serena project created for milpbookLM (no language servers — docs-only repo for now).
- "Big Pickle" verified as a real external provider name (OpenCode stealth model, baseline README:85-87), NOT anonymization.

## Process log (cont. 8 — execution amendments, 2026-09-18 post-maintenance)

- [x] User directives (binding, supersede plan execution details where they conflict): (1) MCP-TOOLS-FIRST in EVERY subagent prompt — name serena (find_symbol/get_symbols_overview/find_referencing_symbols/replace_symbol_body/execute_shell_command), codegraph, tldr, lsp_diagnostics, glob/grep/read; bash = LAST resort (now permission-enforced: cat/head/tail/grep/ls/find/diff/wc/sed + inline python/node evals all DENIED). (2) Concurrency: max TWO active agents (user first said one, immediately corrected to two-as-before). (3) PROTOTYPE-FIRST: postpone all test-writing + everything not needed for a working first prototype with most functionality; full test/evidence battery lands in a SECOND WAVE. Manual hands-on QA by agents is NOT deferred — agents still prove functionality works by running it.
- Execution consequences: VER-test batteries are no longer per-task gates; per-task completion = functionality demonstrably working (manual/hands-on evidence, e.g. service runs, migration applies, endpoint answers) + lint/type/pipeline stays green where already wired. Existing written tests may be RUN as cheap functional probes but no NEW test files, no VER-evidence batch bookkeeping, no mutation QA in wave 1. F1-F4 and gate tasks reinterpreted at prototype scope until second wave.
- State: T1 done+verified. T2 claimed (dd77af1) — verify at prototype scope (extractor/capability tooling works = run the two --check commands). T3 WIP resumes now under amended scope (schema+migrations+harness functional; SKIP writing the 5 unit/db + 2 contract test files; running the already-written 20 invariants ONCE as a functional probe is allowed if cheap, else defer).

## Process log (cont. 9 — T3/T4 close-out + two inference outages, 2026-09-18/19)

- [x] Concurrency further reduced (user): ONE active agent at a time ("no more parallel agents for now" superseded the two-agent rule; ledger + decisions.md updated, d5ccab4).
- [x] T2 VERIFIED at prototype scope (extractor --check 507/507 + 12 narrative; capability registry 61; pytest meta+architecture green after allowlist fix) and T3 VERIFIED (fence-clean commit adef1e2; my own gate re-runs; hands-on migration smoke: roles idempotent, alembic up/down/up, app DML ok / DDL denied, 39 tables; probe 7-pass/13-fail all harness-cleanup mechanics deferred to wave 2). Plan 3/59 (7472267).
- [x] OUTAGE #1: ALL subagent dispatches died with "Cannot connect to API" — root cause chain: host maintenance reboot killed the manually-launched llama-server (:8009) AND unmounted /mnt2 (models + ik_llama.cpp build live there; sudo password-gated). User restored server (now serving ~/ai/ai/Swift-Qwen3.8-27B-Q6_K.gguf) without remounting /mnt2 — local GGUF fallback. Casualty: opencode's bundled rg (~/.cache/opencode/bin/rg) vanished -> glob tool broken; use serena_find_file / bash echo-globs.
- [x] T4 saga: original worker did ~90% then died mid-QA (3 failures logged); TWO session resumes died (API down / empty return); user revealed THEY had killed some spawns ("just resume the agent. i killed it"); fresh-session dispatch COMMITTED 47d6bd4 (QA 41/41 green incl. the 3 prior failures, D12 sweep kept 55 bonus unit tests all green) but its final message was lost to OUTAGE #2 (server died again right after the commit). I verified independently: fence clean, import-linter 4/0 (88 files), mypy clean, ruff clean, pytest meta+arch+unit = 127 passed, harness PG torn down. Plan 4/59 (6bbb9ed).
- Standing lesson: worker "aborted"/empty returns can be USER interrupts — ask before assuming infra. And: verify even "lost" work — the commit existed though the DoneClaim never arrived.
- BLOCKED-HOLD: :8009 llama-server down again (outage #2, unresolved). All dispatches wait on user restart or explicit alternate-provider authorization. T5 (FND-05 jobs/leases/outbox/SSE) dispatch-ready. No `- [~]` marks made — tasks are not input-blocked; the execution substrate is.

## Process log (cont. 10 — T5/T6 close-out, 2026-09-20)

- [x] T5 closed at `e6486a0`: FND-05 jobs/leases/outbox/SSE/capacity classes verified; baseline 127 tests, mypy/ruff/import-linter green; plan 5/59. D13 light-QA + stop-after-agent gating recorded.
- [x] User authorized T6. Initial T6 task call was interrupted after leaving partial files; its continuation could not be controlled. Per user instruction, Atlas played a spoken PulseAudio TTS alert (not an alarm tone) and started a fresh replacement session `ses_f43179968ffepLH1OAX9H6k3KT`.
- [x] T6 implementation commit `2bb96eb`: immutable content-addressed filesystem BlobStore, PostgreSQL object/reference bookkeeping, integrity-verified reads, reconciliation classifications, delayed GC, maintenance CLI, and `blob.integrity_scan` handler.
- [x] Independent line-by-line review rejected the first claim and found defects gates missed: finalized-row GC mutation violated the FND-03 trigger; record-only GC could fsync a missing bucket; immediate temp sweep could unlink an active write; temp-unlink and new-bucket parent fsync ordering was incomplete.
- [x] Same replacement session fixed all findings in `982c644` + `079dd68`; evidence wording aligned in `4cbd15c`. Final protocol uses `os.link` no-overwrite, file+bucket+objects-parent fsync, post-unlink tmp-dir fsync, DB commit last; temp and final deletion share the >24h safety delay; missing references remain incidents and never empty content.
- [x] Atlas verification: read every changed file plus table/trigger authority; ruff clean; mypy clean; import-linter 4 kept/0 broken over 114 files/491 dependencies; existing suite 127 passed; evidence JSON parses; CLI help exposes all blob commands; unsafe 24h GC delay rejected cleanly. Worker live scratch-PG smoke proved put/get byte identity and all three reconciliation classes; no services left running.
- [x] LSP note: domain file clean; package files surface the repository's known editable-install resolution noise while configured mypy is authoritative. Project scan also requested unrelated global Biome; installation was declined because the user did not authorize global tooling.
- [x] T6 marked complete; plan now 6/59. Per D13, STOP before T7 and wait for explicit user instruction.

## Process log (cont. 11 — T7 close-out, 2026-09-20)

- [x] T7 implementation `f063331` (worker `ses_f4269add8ffeTInbyvUzFmwu3d`): correlation/trace context, redacting structured logging, bounded metrics registry, append-only audit + retention report, XChaCha20-Poly1305 credential cipher with versioned keyring + resumable rotation, credential maintenance CLI, CSP/security-header baseline. That session later became uncontrollable across interrupts; per user instruction a fresh replacement `ses_f409f2a8cffeK9nxQC7b8djeSV` took over (spoken TTS alert used for the earlier unresponsive worker per user preference; looping alert + stop honored around the replacement's completion).
- [x] Independent line-by-line review of all 31 changed files found six defects the gates missed: `_is_hex` rejected valid repeated-nonzero W3C ids; tracebacks escaped redaction; pre-existing handlers could emit unredacted duplicates; credential lifecycle emitted no audit rows; keyring mode unchecked (stat/read race); unhandled 500s lacked correlation/security headers. Replacement session fixed all in `2c28b52`.
- [x] Phase-1 re-review found ONE remaining defect: absent-header requests got TWO generated identities (correlation middleware resets the ContextVar in `finally`; the outer error middleware regenerated). Fix: persist the effective context tuple in per-request ASGI state; error boundary rebinds it. Session died at usage limit after applying the edit + evidence; three dispatch attempts across two models then failed with "Cannot connect to API" (subagent outage #3).
- [x] Per standing directive, Atlas completed the remaining verification directly (fix already implemented by delegation): independent TestClient smoke 14/14 PASS (one identity across endpoint context, error log, 500 headers; verbatim echo; uniform scrubbed 500); ruff/mypy (95 files)/import-linter 4-0 (130 files, 570 deps)/pytest 127 passed. Over-strict smoke probe corrected: bare unclassifiable strings are not redactable by design — scrub targets form-shaped secrets (Bearer…, keyword=value) + sensitive key names.
- [x] Committed `bfd62c1` (worker-authored fix + evidence + learning 11); T7 marked complete; plan 7/59. Next: T8 (OPS-01a rootless podman compose).

## Process log (cont. 12 — T8 close-out, 2026-09-20)

- [x] Subagent outage #3 (5 consecutive connection failures across deep/unspecified-high models). TTS alert loop used per user's new standing rule (loop on any stall that blocks continuation; spd-say voice). T7 remainder finished by Atlas within mandate (verification/evidence/commit only).
- [x] User re-prioritized: working prototype is top priority, everything else waits (reaffirms D12).
- [x] T8 dispatched fresh after user restored API; worker session `ses_f405d40c1ffeIc6jF0Oan67dX5` delivered 9 commits (7a7c3d9..fb65731): health/diagnostics routes, rootless 7-service compose, digest-pinned Caddy 2.10.2 + SearXNG, Quadlet/systemd units, fail-closed installer, host probes + committed facts.
- [x] Atlas verification: read all 20 changed files; gates green (ruff incl. probe-host.py, mypy 96 files, import-linter 4/0 over 131 files/581 deps, 127 tests); installer reproduced fail-closed exit=4 execution_enabled=false; own TestClient smoke 6/6 (live 200, ready 503 bounded reason, security+correlation headers on health routes, anonymous diagnostics 401); YAML valid.
- [x] Real host facts recorded: 2× Radeon VII + RTX 3080 Laptop + Cezanne iGPU; ROCm 7.15 HIP; CUDA 13.1; driver 595.99.02; Vulkan 1.4.304; HSA_OVERRIDE_GFX_VERSION=9.0.0 makes rocminfo report gfx900 for gfx906 cards (recorded for tasks 10/42).
- [~] T8 marked `- [~]`: single deferred item = live `podman compose up` drill (sudo-gated install; user commands in infra/podman/README.md). Plan 7/59 done + 1 partial. Next: T9 (SCOPE-GUARD) at prototype scope.

## Process log (cont. 13 — T9 close-out, 2026-09-20)

- [x] T9 at prototype scope: worker `ses_f404660e9ffegRWlNio4hasRv0` delivered 5 commits (63893f1..a474595) — domain capability value objects + effective-state computation (fail-closed: unknown dependency = unhealthy, provisional never available, non-targets excluded), registry packaged as runtime resource under milpbooklm_contracts (tools/ paths updated, no product→tools import), public GET /api/v1/capabilities wired with env-driven flags/providers.
- [x] Atlas verification: read all changed files; gates green (ruff, mypy 100 files, import-linter 4/0, 127 tests); own default-registry smoke: anonymous 200, 57 capabilities, non-targets absent, bounded vocabulary, headers intact. Initial smoke "failure" was a wrong expectation — registry seed has 0 implemented entries, so degraded branches require synthetic definitions (worker's probe covered that path; code-reviewed).
- [~] T9 marked `- [~]`: endpoint done+verified; advertisement-scan/flag-obligation meta-tests are wave-2 test-writing scope per D12. Ledger + close-out `d8bf5ea`. User re-affirmed prototype-first twice during verification. Next: T10 MOD-01.

## Process log (cont. 14 — T10 close-out, 2026-09-20)

- [x] T10 saga: original worker died at usage limit mid-task (substantial uncommitted work); resume quota-dead; two restart attempts stalled ("Loading model") — root cause: the subagent model routes through the LOCAL llama-server, which the user restored; TTS-loop alert discipline applied per standing rule (user later requested tts stop). Fresh takeover `ses_f401354e2ffe9qP2vuVHtprSJS` delivered 4 commits (3c96066..691186a).
- [x] Worker REPAIRED real defects in the abandoned code: GPU-gate refcount now reserved under the gate before the slow start; RetryPolicy got its consumer (BoundedChatDispatcher — retry only before visible output, restart never concatenate); 408→TIMEOUT; preemption wired into WorkerLoop (running_jobs + InteractivePreemptor parks media via ch15 CAS with lease release — respects ck_jobs_lease_consistency per FND-05 lesson); deps verified authorized (httpx=HTTP row, pydantic=API line, anyio declared explicitly).
- [x] Atlas verification: read all 19 changed files; gates green (ruff, mypy 112 files, import-linter 4/0, 127 tests). First-hand smoke: LIVE llama.cpp streaming (24 monotonic seqs, Accepted-first, Delta→Usage→Completed, model obeyed "reply with exactly: PROTOTYPE OK"); routing local-first + local_only + unapproved filtering; single-flight 2→1; media blocked while chat hot → loads after release → idle-hot evicted → cold-media stopped at zero refs; quota no-retry; timeout exactly-to-bound backoff.
- [x] Atlas smoke-harness lesson: three hangs were MY probe bugs (slots dataclass `__dict__`, anyio inner task-group join semantics, leaked refs from the single-flight probe keeping the GPU gate correctly closed). Minimal repro isolated product correctness — the concurrency design fail-safes exactly as specified.
- [~] T10 marked `- [~]`: prototype-complete; deferred = contract-suite test files, recording mode, p95 assert, full ADR, non-chat adapter methods, ModelHealth→capabilities cross-process seam. Ledger + close-out `3672179`. Plan: 7 done + 3 partial /59.
- NEXT: T11 (Phase-0 gate — reinterpret at prototype scope per journal cont. 8) then T12 ING-01a (acquisition/quarantine — prototype critical path).

## Process log (cont. 15 — T11+T12 close-outs, 2026-09-20/21)

- [x] Naming trap closed: `.omo/` artifact paths unified to `milpbooklm` (commit `364e9a3`, agent-executed per user request); guide dir stays `milpbookml-implementation-guide` (matches disk + zip branding). D14 (bge-m3 embeddings on CPU for prototype; escalate to 2nd Radeon VII only if slow) + D15 (direct route T11→T18; D13 dispatch gating superseded) recorded in decisions.md.
- [~] T11 marked `- [~]` (`32dfe8f` + close-out `eca0c85`): gate report `artifacts/verification/phase-0-gate.json` (10 workstreams, honest), conformance v0 (`artifacts/conformance.json`, 61 caps, 0 advertised — fail-closed honest), suites 127 green; PHASE-GATE-001 suite doesn't exist → reported deferred (not faked). NOTE: boulder's "already complete" reminder was WRONG — checkbox was still `- [ ]`; always read the plan.
- [~] T12 marked `- [~]` (`e54b466` + close-out `42bfe73`): full ING-01a acquisition stack first-hand verified by my own 11-check driver (dedup, sniffing-wins, encrypted-PDF policy_blocked, job terminal+lease-cleared, CAS rename, tombstones, cross-user isolation, global blob dedup, audit). **Incident**: the worker, after finishing T12, rolled into T13 WITHOUT dispatch (3 commits incl. new test files violating D12) — reverted via `git reset --hard e54b466` (recoverable: fa12282 CanonicalDocument contract + 645e4c4 text parser via reflog). Lesson: dispatch prompts now carry explicit task-number discipline + stop-at-end instruction.
- Nits parked for T13: foreign-notebook write 403 `deny:not_member` (existence disclosure vs 404 pattern); uuid4 app ids vs uuidv7 defaults; MAX_ACQUISITION_BYTES → typed config key.
- Scratch PG left RUNNING at /tmp/opencode/t12-qa socket port 29519 db milpbooklm_t12 (blob-root co-located) — reusable by T13 QA.
- NEXT: T13 ING-01b (parse→canonicalize; parser isolation subprocess; PDF chain deps need REFERENCE-DEPENDENCIES + ver-arch-03-001 policy rows).

## Process log (cont. 16 — T13 close-out, 2026-09-21)

- [~] T13 marked `- [~]` (worker session `ses_f3f0a4724ffeSONjJU7Ao4hj6z`, 8 commits through `898d04f`, close-out `39ab088`): canonical contract + deterministic text/PDF parsers + rootless isolated child (network imports blocked, RLIMITs) + PG persistence + worker wiring + both T12 nits folded. **Verification drove TWO real fixes**: (1) `eec1b48` migration 0002 not idempotent — 0001's `create_all` from live metadata collides with 0002's raw SQL on fresh DBs (fresh-install breaker); (2) `898d04f` two-writer job race — API's synchronous acquisition-job lifecycle vs the polling worker = `JobCasConflictError` 500s under any deployment with a worker running (latent since T12, only visible hands-on). Final orchestrator smoke: 11/11 PASS (multilingual DE+JA canonicalization, PDF page/paragraph nodes with extracted text, reparse-stable UUIDv5 IDs matching DB, explicit corrupt state, race gone).
- Environment anomaly recorded: **/tmp served inconsistent content to different processes** during T13 verification (scratch dirs vanished; a driver helper's execution returned bytes its own verified source+co_consts could not produce, while the same code path in another process was correct; shell-authored file fixtures were unaffected). All verification scratch moved to `/home/srcds/dev/*-smoke` (same ext4 as the repo); drivers use od-verified FILE fixtures, not python-generated ones. Unresolved whether this is the same phenomenon as the earlier plan-file ENOENT episode; treat /tmp as untrusted for verification artifacts.
- Scratch PG for T14 left RUNNING: `/home/srcds/dev/t13-smoke` socket, port 29521, db `milpbooklm_t13` (schema at head, T13 rows present), blob root co-located. Valid PDF fixture at `/home/srcds/dev/t13-smoke/fixture.pdf` (pdfplumber self-tested).
- NEXT: T14 ING-01c (provenance graph, activation transaction, basic Source Guide) — CP1 checkpoint (upload → canonical text) is now FUNCTIONALLY REACHED at the API level.

## Process log (cont. 17 — T14 close-out, 2026-09-21)

- [~] T14 marked `- [~]` (worker `ses_f3e8842b3ffen8MQwwMvj174Ri`, commits `4b3be3b`+`24bd37f`, close-out this entry): provenance edges (closed 6-type vocabulary, 10-col identity uniqueness, immutable endpoints + narrow canonical active-flip exception), bounded cycle-safe traversal, full-input-keyed restriction cache, single-transaction activation (demote→promote, CAS, row-lock serialization), deterministic Source Guide v1, migration 0003 idempotent by construction. Three dispatches needed: first interrupted, second died at usage limit mid-WIP, third took over the uncommitted tree, found a swap-order bug in the WIP (promote-first would UniqueViolation every refresh), and finished.
- Atlas independent smoke: **ATLAS_T14_PASS 19/19** (driver `/home/srcds/dev/t14-atlas/atlas_t14.py` — includes a fresh-source concurrent-activate probe; the naive same-source variant is invalid because the first activation already consumed the CAS). Immutability triggers verified from SQL as superuser: edge UPDATE/DELETE blocked, canonical content tamper blocked, active/activated_at flip allowed.
- API QA recipe corrections recorded in ledger (Origin header on every unsafe call; flat /api/v1/sources router; notebook_id as query param; /paste for titled text).
- NEXT: T15 IDX-01 (chunking, FTS EN/DE, pgvector embeddings, generations, fusion). Prereq check first: bge-m3 GGUF availability for the embedding endpoint (D14: CPU Q8; escalate to 2nd Radeon VII if slow). Then T16→T17→T18 per D15 route.

## Process log (cont. 18 — T15 close-out, 2026-09-21)

- [~] T15 marked `- [~]` (worker `ses_f3e22f3f2ffemkdg2hQ9OWihID`, 8h run, commits `09570f1`..`4b4c6a7` + verification fix `cb63de8`; close-out this entry). CP2 (search) functionally reached: hybrid lexical+vector+RRF search over activated sources, authz-in-query with post-hydration recheck and over-fetch ladder.
- **Embedding endpoint provisioned by orchestrator** (no user dependency needed after all): bge-m3-Q8_0.gguf (635MB) downloaded from gpustack HF mirror to `/home/srcds/ai/ai/`, served on CPU `:8010` via the existing uf3 llama.cpp build (`llama-server --embedding -ngl 0`). pgvector 0.8.2 was already installed in PG17. D14 escalation (2nd GPU) not needed at prototype corpus size.
- **Verification catch #3 this session**: `command.mode is RETRIEVER_LEXICAL` — string-identity routing on JSON-derived mode made every lexical/vector search silently run FUSED. Behavioral proof: exact-match English lexical query returned all 3 notebook sources (German + "Hello canonical world." PDF cannot lexically match) while the port's exact SQL returns 1 row. One-line fix (`==`) via quick worker `cb63de8`; my re-smoke then ATLAS_T15_PASS 22/22. Lesson appended by worker: never `is`-compare request-derived strings (CPython only interns identifier-like literals at compile time, not JSON-parsed values).
- Worker's own QA had also found a real rebuild bug pre-commit (id-alone PK on index_chunks → UniqueViolation on re-chunk since deterministic chunk ids repeat across generations → composite PK `(index_generation_id, id)`).
- BM25 gate honestly REJECTED (ADR-0001: PG FTS parity on locked corpus, stays unlabeled); HNSW honestly NOT ENABLED at 9-row prototype scale (ADR-0002: planner picks seqscan, recall 1.0, revisit ~10k vectors).
- Known prototype gap (recorded, non-blocking): pasted-text language = 'und' → fts_config 'simple' fallback; EN/DE configs engage when language is set (PDFs with detected language or future language detection).
- NEXT: T16 RAG-01a (retrieval pipeline → answer contract + citation validator). CP3 approach; needs the chat model — the GPU llama-server on :8009 (Swift-Qwen3.8-27B) is the natural completion endpoint, already serving.

## Process log (cont. 19 — T16 close-out, 2026-09-21)

- [~] T16 marked `- [~]` (worker `ses_f3c10c345ffe3R1jkY0E3DISzA`, commits `33351e3`+`2742446`; two prior sessions stalled early — the fresh-dispatch takeover pattern worked again, 18 min). Grounding layer complete: manifest freeze → pinned hybrid retrieval → quota/budget assembly → structured provider contract → 5-check citation validator → atomic publish / explicit abstain → pinned citation jump with unavailable-(purged) state.
- Atlas re-ran the worker's QA driver first-hand (fake-contract): valid publish atomic (+1 row), invented id → zero rows, abstain → no row, cross-notebook rejected, purged jump/publish correct. Gates green (mypy now 152 files, pytest 127).
- **GPU llama-server :8009 is DOWN** (connection refused; confirmed during worker QA and twice by Atlas). It serves real-model completions AND this orchestration's subagent routing (recent workers rerouted via gpt-5.6-terra upstream and still completed). Real-model grounded smoke deferred — fold into T17 verification once the user restarts it. Orchestrator must not touch that server (standing rule).
- NEXT: T17 RAG-01b (conversations, streaming, chat config/lifecycle) — build on the grounding seams; needs :8009 up for real streaming chat QA. Then T18 (UI-01) = CP4.

## Process log (cont. 20 — T17 close-out, 2026-09-21)

- [~] T17 marked `- [~]` (worker `ses_f3bdafa3fffeM9G1VI2URYI6xQ`, commits `427be9f`..`369755c`; close-out this entry). CP3 fully reached at the API level: private conversations with SSE streaming, cancellation, reset/new, config (style/length, DE/EN), manifest-pinned instructions + selected notes, grounded notebook overview (cited summary + suggested questions), AD-011 disclosure shape with tool-free ordinary path.
- **Routing incident resolved by user**: the `:8009` GPU llama-server outage had silently failed deep-worker routing over to a remote terra upstream with ~5-12 minute per-session windows — five stalled-but-honest dispatches across T16/T17, each closing real gaps then wrapping with "could not complete within this turn". User switched deep routing to **gpt-5.6-sol**: the very next fresh dispatch finished the whole remaining task in 22m33s. Lesson recorded: when workers across tasks suddenly all "block" after uniform short windows, suspect the model routing/quota layer, not the tasks. `:8009` remains down (user-managed); real-model streaming QA deferred to T18.
- Atlas re-ran the full QA driver first-hand (`task_17_manual_qa.py`, live worker + CPU bge-m3): all assertions, driver_rc=0 — including the SSE invariant (terminal fires only after the validated persisted message; REST resync equals terminal state) and the no-duplicate/no-ephemeral-history properties.
- Noted in passing: retrieval logs show expected over-fetch ladder behavior on the tiny fixture corpus (1-2 rows vs top_k=30) — correct by design (authz filters never relaxed), just noisy at prototype scale.
- NEXT: T18 UI-01 (React shell: notebooks/sources/chat, job store, source viewer, a11y baseline, E2E harness) = CP4, the last prototype-route task. Wants :8009 up for E2E with the real model; fake-provider path remains available regardless.

## Process log (cont. 21 — T18 close-out + scratch consolidation, 2026-09-21)

- [~] T18 marked `- [~]` (worker `ses_f3ba4214bffeJQL3L6FlKTM89m`, commits `b2e15ca`+`d98692b`). **CP4 REACHED — the direct prototype route (T11→T18) is COMPLETE: register → notebooks → upload/paste → parse → activate → index → grounded streaming chat with validated citations → sandboxed source viewer, all in a browser.**
- T18 needed 3 dispatches: two usage-limit deaths after building the scaffold; orchestrator ran the mechanical verification first-hand between dispatches (tsc strict clean, vite build with route splitting, Python gates, full route-assumption audit vs the API) and handed a defect list (broken seed script constraint, wrong types-URL default, missing notebook-create route) to the final worker, which fixed all three and completed the 13/13 web-origin smoke + 12/12 chromium/firefox browser pass. :8009 returned mid-task (final worker routed via local llamacpp) — real-model UI pass now unblocked.
- **Scratch consolidation per user order** (`6f54fe9`): all eight agent scratch dirs moved from `~/dev/` into `milpbookLM/scratch/` (gitignored); live t13-smoke PG relocated cleanly (schema 0006, data intact) and left RUNNING on new socket `<repo>/scratch/t13-smoke:29521`; committed path refs fixed; **standing convention recorded in learnings.md: ALL agent scratch lives exclusively under `milpbookLM/scratch/` — nothing outside the repo.**
- Notable honest-limitation surfaced by QA: the capabilities registry is a frozen spec seed, so the UI create-notebook affordance is disabled-by-design with the registry reason shown; the REST route works. Registry seeding is wave-2 gate work.
- Remaining plan: 19 (MOD-01b ADR pack), 20 (PHASE-GATE), then wave-2 hardening — all post-prototype-route. Wave-2 deferral ledger now spans T8–T18 test batteries, E2E/CI harness, real-model passes, registry seeding, HNSW-at-scale, purge flows (T24), etc.
- HALT: user ordered a stop after the cleanup agent finished. No further dispatches until the user says go.

## Process log (cont. 22 — T19 close-out, 2026-09-21)

- [~] T19 marked `- [~]` (worker `ses_f3aaddf7...`, commit `b1ea2b3`). MOD-01b complete under D16: ADRs 0003-0005 (six-field records), corpora v1 (5 kinds × 20 DE + 20 EN), EVAL-GATE-001 harness, typed routing config + test. All verified first-hand by orchestrator: harness PASS (recall 1.0/1.0/1.0 @1024d), gates green (pytest 128).
- D16 born this session: user stopped a Glimmer-30B download ("just use the prod config with what we already have") — local chat selection = Swift-Qwen3.8-27B-Q6_K on the prod gfx906 stack; ADR 0003 records the substitution. Zero acquisitions; disk at 97% independently forbids them.
- External probes honest: Big Pickle 403 (free tier client-restricted), Muse Spark 401 (no creds) → degraded local-only routing recorded per plan; never faked.
- Session ops: user freed the GPUs and authorized bringing up llama.cpp — orchestrator now runs the prod config on :8009 (PID file scratch/llama-8009.pid); one crash (HIP graph abort) recovered by restart + verified with a real completion. Orchestrator self-inflicted a session-host kill by misreading a post-compaction restart as an orphan (lesson recorded in learnings: verify ses ownership against run-continuation churn before killing). A 20h-wedged serena MCP server (95% CPU) was the actual stale process.
- Aborted dispatches CAN leave a spawned session + WIP (twice today); resume-by-task_id (user: "subagent needs a resume") carries them home. PROGRESS.md-in-scratch now standard for crash-resilient resumes.
- NEXT: T20 Phase-1 gate (blocked-by 12..19 — all now done/verified-partial). Wants the real rootless deployment + real local models; T8 podman drill remains user-sudo-gated — gate may need the user for the deployment leg or run evidence on the scratch stack.

## Process log (cont. 23 — T20 close-out: PHASE-1 GATE PASSED, Wave 1 complete, 2026-09-21)

- [~] T20 marked `- [~]` (workers `ses_f3a8698d8` usage-limit death → `ses_f3a73ed8` takeover 14m30s; commit `a16ddda`). E2E-001+002 text/PDF legs green on BOTH browsers with the real Swift-Qwen model; gate report 15/15 capabilities, 0 blocked; grounding locator enrichment committed with it.
- **WAVE 1 COMPLETE**: T1–T20 done (7 [x], 13 [~]); prototype + Phase-1 gate on real local models. Everything remaining is Wave 2 (T21+: office families, EPUB/fetch, research, hardening, tests).
- Orchestrator verification survived TWO host reboots mid-flight: stack recovered each time (pg_ctl from scratch/t13-smoke/pgdata → bge :8010 → API → worker → vite; :8009 user-managed, already up both times). Final first-hand E2E rerun: rc=0 PASS both browsers. Committed evidence file restored after rerun; rerun logs kept in scratch/t20-gate/.
- Post-reboot UI lesson: a vite dev server dying mid-session leaves browser proxy fetches hanging forever — the SPA boots to `Loading view...` and never settles; symptom looks like an app hang but is dev-infra death. Check port liveness FIRST when the SPA sticks at boot.
- User hard rule (2026-09-21, permanent): the Swift-Qwen llama.cpp server is shared pre-existing infra — consume only, never spawn/restart/duplicate when one is up.
- HALT per user order after T20: stop and wait for instructions. Stack left RUNNING for the user: PG :29521 (scratch), :8009 (user), :8010 embeddings, :8000 API, :5173 web, worker t20-w1 — pidfiles in scratch/t20-gate/.

## Process log (cont. 25 — T22 close-out, 2026-09-22)

- [~] T22 marked `- [~]` (4 worker sessions: 2 aborts + usage-limit death + finisher; commit `4655dc8`). ING-02b complete: hardened fetch service (SSRF-pinned transport on the only connect path), EPUB + HTML families with hostile corpora, web locators, 18-test denial suite.
- Orchestrator verification: all gates green first-hand (mypy 174 / pytest 154+26); live SSRF probes all refused pre-connect with stable reasons; port allowlist stricter than plan text.
- Routing observation: quick-category dispatch died INSTANTLY at usage limit (remote upstream); deep category ran on local llamacpp/:8009 fine. When limits hit, dispatch deep, not quick.
- HALT per user order (stop after T22): 22/59 tasks done (7 [x], 15 [~]), 37 remaining (T23+ wave 2). Stack live: PG :29521, :8009 (user), :8010, :8000, :5173, worker.

## Process log (cont. 26 — T23 close-out, 2026-09-22)

- [~] T23 marked `- [~]` (4 sessions, commit `d6a6473`). Images+OCR (deu+eng, bbox locators, rank-1 search proof), A/V probe (ms locators, container allowlist), public-video honest states — all live-verified. STT deferred (no whisper assets; D16; user decision pending).
- Agent-server instability defined today: two workers finished real work but degenerated into slash-walls at their final report; one abort. User fixed the server twice + ordered TTS alert protocol on agent death (scratch/alert-loop.pid; kill via pkill -f "while true; do spd-say" + pkill -x spd-say). Finisher-dispatch pattern (fresh deep session: gates+evidence+commit only) proved again — 54m for T23 after 6h+ of chaos.
- OCR serving detail: worker needs TESSDATA_PREFIX=scratch/t23-ocr/tessdata (system tessdata lacks deu) — start-worker.sh must carry it for media parsing.
- Progress: 23/59 tasks (7 [x], 16 [~], 36 [ ]). Pausing for user review per cadence.

## Process log (cont. 27 — T24 close-out, 2026-09-22)

- [~] T24 marked `- [~]` (commit `1ef1270`). Refresh semantics, all-families rebuild proof, identity-based purge closure with transactional tombstones + async erase + report, purge-closure acceptance test, expanded hostile/eval corpora. Verified first-hand: gates green (mypy 180 / pytest 161+12), purge test PASSED.
- The interrupted dispatch actually COMPLETED before its abort — PROGRESS.md + commit told the truth the aborted report could not. Third such pattern today: trust committed state, not agent reports.
- Progress: 24/59 tasks (7 [x], 17 [~], 35 [ ]). Next: T25 Phase-2 gate (universal ingestion evidence).

## Process log (cont. 28 — T25 close-out: PHASE-2 GATE PASSED, 2026-09-22)

- [~] T25 marked `- [~]` (worker `ses_f36963cf2`, commit `f1c0bfe`). All 11 ingestion families evidenced (isolation/goldens/lifecycle/retrieval), E2E-002 heterogeneous journey green with real-model heterogeneous citations, disabled connectors honestly not-advertised.
- The journey exposed a real T16 defect: publication validator required char-extent coverage from structural locators (bbox/slide/sheet) which have none — every phase-2-family citation would have been rejected. Fixed via identity+authz path for NULL-extent locators (authorization untouched, verified by orchestrator diff read).
- Progress: 25/59 tasks (7 [x], 18 [~], 34 [ ]). Phase gates: 1 PASSED, 2 PASSED. Next: T26 RSR-01a (SearXNG service + adapter) — wave 3 begins (research surface).

## Process log (cont. 29 — T26 close-out, 2026-09-22)

- [~] T26 marked `- [~]` (worker `ses_f3676635`, commit `1fd6a89`). SearXNG adapter + deterministic fake + cache + budgets green; real smoke deferred (T8 podman class).
- Cross-cutting find: frozen+slots dataclass exceptions break under anyio deadline scopes (contextlib __traceback__ reassignment) — T22 fetcher bug fixed w/ regression test; two more latent shapes flagged to owners.
- Progress: 26/59 tasks (7 [x], 19 [~], 33 [ ]). Wave 3 (research surface) underway. Next: T27 RSR-01b research runs — the largest single task in the plan (state machine + 7-tool surface + injection hardening).

## Process log (cont. 30 — T27 close-out, 2026-09-22)

- [~] T27 marked `- [~]` (worker `ses_f366167a3`, commit `b047bb2`). Research runs live: durable state machine, exactly-seven-tool surface, immutable evidence, injection corpus fully denied server-side (live 30 tool.denied rows), E2E-008 green on fake web, migration 0008 idempotent both paths.
- Progress: 27/59 tasks (7 [x], 20 [~], 32 [ ]). Next: T28 RSR-01c Playwright browser worker + deterministic local web (user-space worker now; container form T8-class deferred — Chromium+Firefox already installed from T18/T20 E2E).

## Process log (cont. 31 — T28 close-out, 2026-09-22)

- [~] T28 marked `- [~]` (worker `ses_f362dd8f`, commit `25a9cc0`). User-space Playwright browser worker live: sandbox posture PROVEN (Playwright default = silent --no-sandbox — caught and forced correct), T22-table route guard, disposable contexts, quarantine downloads, automation gate; E2E-008 browser leg green.
- Progress: 28/59 tasks (7 [x], 21 [~], 31 [ ]). Research surface (T26-T28) complete except T8-class deployment forms. Next: T29.

## Process log (cont. 32 — T29 close-out + HALT, 2026-09-22)

- [~] T29 marked `- [~]` (3 sessions through 2 usage-limit deaths; final finisher `ses_f35b7b79e` 20m; commit `4cfeaea`). User-space EXE-01 core complete: signed nonce-bound broker protocol, bwrap sandbox w/ delegated cgroups, CAS images, validated outputs pipeline, REAL-bwrap escape suite green + manual denial proofs. 4 new boundary defects found+fixed during QA (tmpfs quota ordering, swap leak, cgroup-attach race, corrected seccomp host fact).
- Admin deployment forms + D11 GPU benchmark bundle deferred (user window + D16 authz) — ADRs 38/42 consume later.
- Progress: 29/59 tasks (7 [x], 22 [~], 30 [ ]). Gates at 4cfeaea: ruff clean / mypy 208 / import-linter 4-0 / pytest 246 + 12. Wave 3 nearly complete — T30 (Phase-3 gate) is next and unblocked (T26-T29 evidence ready).
- HALT per user order after T29. Stack live (PG :29521, :8009 user-managed, :8010, :8000, :5173); prototype usable at localhost:5173.

## Process log (cont. 33 — user-requested capability surfacing, 2026-09-22 eve)

- User asked why notebook-create was still absent in UI. Root cause chain: UI gates on capability `state==="available"`; registry seed marked ALL 61 entries implemented:false (day-one placeholder, never flipped); plus stale health constants (schema head pinned 0001_baseline; PG-major 18 vs dev 17) degraded the postgresql dependency.
- Fix `98b14f7` (deep worker, 15m): 20 live capabilities flipped in registry+seed lockstep (check_capabilities green); schema head now derived from migrations; `MILPBOOKLM_REQUIRED_POSTGRES_MAJOR` env override; provider mapping fixed in composition; +9 tests (255 canonical now).
- Atlas wired dev env into scratch/t20-gate/start-api.sh (PG 17 + 20 cap flags), restarted API: 20 available incl. notebook_management+grounded_chat; health database/schema/blob ready (execution_prerequisites honestly degraded until prerequisites.json provisioned).
- Browser QA (node playwright, scratch/t-qa/): create button VISIBLE+ENABLED, notebook created via UI, chat panel no longer blocked. Evidence: scratch/t-qa/01..05.png.
- Not flipped (honest): agentic_chat, code/execution caps (engine unwired), voice/STT, pdf+paste flags (parsers live, outside delegated set — flip on request).

## Process log (cont. 34 — web session-invalidation hardening, 2026-09-22 late)

- User hit "Notebook creation failed" from a stale session (API restart churn invalidated cookie HMAC chain; client never noticed). Root cause: auth checked once per page load; no global 401/403 handler; react-query cache masked decay.
- Fix `a52a887` (deep worker, 10m): ky afterResponse hook — 401 any / 403 {origin_rejected,csrf_rejected} exact allowlist → reset CSRF + notify registry; auth provider clears actor+query cache (loop-guarded via actorRef); visibilitychange revalidation; 8 vitest tests.
- Atlas E2E proof (scratch/t-qa/ui_revoke_check.mjs + 07/08.png): live login → DB-revoked session → create click → POST 401 → login screen shown, generic error NOT shown; wrong-password stays on login.
- Gates: vitest 8/8 (11 total), tsc build ok, ruff clean, pytest unit 183. Biome pre-existing red on untouched files (useLiteralKeys) — noted, not in scope.
