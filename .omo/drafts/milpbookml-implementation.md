---
slug: milpbookml-implementation
status: drafting
intent: clear
review_required: true
plan_path: .omo/plans/milpbookml-implementation.md
plan_sha256: null
review_round_id: null
pending-action: write and review .omo/plans/milpbookml-implementation.md
review:
  momus:
    status: pending
    workspace_root: null
    runtime_home: null
    target: .omo/plans/milpbookml-implementation.md
    round_id: null
    plan_sha256: null
    launch_id: null
    session: null
    result: null
  independent:
    status: pending
    workspace_root: null
    runtime_home: null
    target: .omo/plans/milpbookml-implementation.md
    round_id: null
    plan_sha256: null
    launch_id: null
    session: null
    result: null
approach: >-
  One decision-complete implementation work plan for the entire milpbookML v1.2 FINAL guide
  (Phases 0-7, 21 workstreams), organized as waves following the PLANNING-HANDOFF workstream DAG
  and phase gates. Every task row (- [ ] N.) carries a hierarchical MICRO-INDEX (up to 4 levels,
  1.1.1.1-style) enumerating every action/sub-step, each leaf mapped to ARCH-/TECH- requirement IDs
  and VER-* verification IDs from requirements.generated.json; plus a master index appendix mapping
  the full numbering tree to tasks. Tasks reference the guide's own verification-group execution map
  (ch.25) for acceptance oracles; no new oracles are invented. User-imposed process rules: journal in
  .omo/journal/, git commits per step, MCP tools before bash for planner AND executor, max 2 delegate
  agents at a time, interview before defaults.
---

# Draft: milpbookml-implementation

## Components (topology ledger)
<!-- Lock the SHAPE before depth. One row per top-level component that can succeed or fail independently. -->
<!-- id | outcome (one line) | status: active|deferred | evidence path -->

- C1 platform-harness | Repo layout, locks/CI, config+capability profile, spec tooling, rootless deployment skeleton, telemetry/security baseline exist and pass meta gates (FND-01/02/07, SCOPE-GUARD, OPS-01 install side) | active | guide: PLANNING-HANDOFF.md, 00/04/20/25 chapters
- C2 data-identity-core | PostgreSQL 18 roles/migrations, domain tables+invariants, local auth+authz matrix, jobs/leases/outbox/SSE, immutable blob store + reconciliation all pass crash/concurrency suites (FND-03..06) | active | guide: 04/05/15/17/19 chapters
- C3 ingestion-retrieval | Text/PDF ingestion through canonical docs, indexing, hybrid retrieval, grounded chat with citations + provider gateway/fakes pass E2E; then all remaining source families (ING-01/02, IDX-01, RAG-01, MOD-01) | active | guide: 06/07/08/09/10 chapters
- C4 research-execution | SearXNG discovery, hardened fetch, Playwright tools, Bubblewrap broker pass SSRF/isolation/recovery gates (RSR-01, EXE-01) | active | guide: 11/12/19 chapters
- C5 studio-media-ui | React shell + source viewer, artifact framework, all text/data/visual/media recipes with provenance/export/study state (UI-01, STD-01/02/03, MED-01) | active | guide: 13/14/16 chapters
- C6 collaboration-release | Sharing/copy/collab gates, production-equivalent deploy/upgrade/restore/NFR/release evidence bundles (COL-01, OPS-01 release side) | active | guide: 17/21/25 chapters

## Open assumptions (announced defaults)
<!-- Record any default you adopt instead of asking, so the user can veto it at the gate. -->
<!-- assumption | adopted default | rationale | reversible? -->

## Findings (cited - path:lines)

- All 26 technical chapters + all meta docs read in full by planner (2026-09-17); independently cross-checked by two explore agents (ch01-09: ses_f53522334ffero0lOqCm3DZk4a; ch10-17: ses_f535222f0ffeQeeQws38S35s5v) - zero contradictions.
- Guide is self-validating: 507 requirement records / 495 normative / 61 capabilities; every record has VER-* ID, test_path, fixture, oracle, tier, evidence_path (requirements.generated.json). Plan must ASSIGN these, never restate or invent.
- Workstream DAG + critical path FND-01 -> FND-03 -> FND-05/06 -> ING-01 -> IDX-01 -> RAG-01 -> STD-01; phase gates 0-7 (PLANNING-HANDOFF.md:36-77).
- Decision deadlines table (PLANNING-HANDOFF.md:80-91): model providers (pre-Phase-1-acceptance), reverse proxy/TLS (pre-Phase-0-production-evidence), backup utility+key recovery (pre-first-RC), OCR/STT (pre-Phase-2-affected), TTS/image/video (pre-Phase-6-affected), BM25 (post-evaluation only).
- Stack fact-check (librarian ses_f533f5265ffeZPmAEVDKmPM3vh + extractor ses_f530b259bffeByaaYMN2W98sCO): every pinned choice is current and non-EOL as of 2026-09-17. Key versions: PG18 GA 2025-09-25 (+uuidv7(), pgvector 0.8.6 PG13+), Python 3.13.15/uv 0.12.9 (uuid module has NO v7 - guide claim correct, TAD-011 holds), FastAPI 0.141.1, Pydantic 2.13.5, SQLAlchemy 2.0.54, Alembic 1.20.0, psycopg 3.3.5, Node 24.21.0 Active LTS (maintenance starts 2026-10-20, EOL 2028-04), pnpm 12.4.2, React 19.3.0, Vite 8.3.0, TanStack Query 5.103.1/Router 1.170.38, podman-compose v1.6.0 (containers org, maintained; PODMAN_COMPOSE_PROVIDER confirmed in podman source compose.go), Quadlet user units supported (.container/.pod/... + podman quadlet install subcommands), SearXNG rolling (formats json NOT default - must be set; limiter requires Valkey), bwrap 0.12.0 (2026-08-26; setuid REMOVED - unprivileged userns mandatory; GHSA-pxhw-h44j-8pfx fixed), cgroup v2 delegation drop-in Delegate=memory pids cpu io, argon2-cffi 25.1.0, PyNaCl 1.6.2 (Aead = XChaCha20-Poly1305-IETF docs-verified), Playwright py 1.63.0 (Chromium 153.0.8010.12/Firefox 155.0), Hypothesis 6.168.0, pytest-asyncio 1.4.0 (pytest>=8.4), Vitest 5.0.1, axe-core 4.13.0. UNVERIFIED: PG 18.x latest minor, patch dates for pnpm/Vite/axe, literal aead_xchacha20poly1305_ietf symbol name. Podman repo org renamed: containers/podman -> podman-container-tools/podman.
- "Big Pickle" is a REAL provider name (OpenCode's free limited-time stealth model), not anonymization (architecture-baseline/README.md:85-87): external replaceable bootstrap/fallback only, never trusted local default.
- Ch10-17 prose contains no inline requirement IDs - traceability comes solely from requirements.generated.json records (chapter-keyed); plan maps tasks to those records.
- Tensions to encode as plan guardrails: (a) ch10 video-gen port vs ch14 "provider video is replaceable scene/render, not data model"; (b) ch11 model-visible tools vs ch12 staged admin-imaged execution - keep separate; (c) uncertain_submission operator states lack /admin route detail; (d) purged citation-jump UX unspecified ("subject to purge state"); (e) worker-media optional with no owning phase - Phase 6 (MED-01) owns it.

## Decisions (with rationale)

## Scope IN

## Scope OUT (Must NOT have)

## Open questions

(interview in progress - asked in batches of <=3, foggiest-gap first; user claimed all forks per "ask everything that is unclear")

Q1 DEPLOYMENT+HARDWARE: which host does this deploy to (this dev machine? separate server?), and what are CPU/RAM/GPU/disk specs? WHY: gates local-model selection (Q2) + NFR reference-profile validity (ch21: 8 cores/16GiB/SSD) + whether Phase-0 production-equivalent evidence runs there.
Q2 MODEL PROVIDERS (guide deadline: before Phase-1 acceptance): local text-gen + embedding reference selection. Options: (a) local-only via Ollama/llama.cpp server, (b) external OpenAI-compatible only (Big Pickle bootstrap), (c) hybrid local-first + external fallback [DEFAULT], (d) decide later, fakes only until gate. WHY: blocks quality/performance fixtures for RAG-01/MOD-01, not platform skeleton.
Q3 REVERSE PROXY/TLS (deadline: before Phase-0 production-equivalent evidence): Caddy [DEFAULT, guide-named] / nginx / Traefik / plain-HTTP LAN-only.
Q4 BACKUP UTILITY (deadline: before first RC): pgBackRest+blob snapshot script [DEFAULT] / WAL-G / pg_dump+rsync / Borg.
Q5 OCR/STT (deadline: before affected Phase-2 tasks): Tesseract OCR [guide reference]; STT: faster-whisper [DEFAULT] / whisper.cpp / vosk; language profile: English-only [DEFAULT?] vs multilingual.
Q6 TTS/IMAGE/VIDEO (deadline: before affected Phase-6 tasks): local (Piper etc.) vs external OpenAI-compatible [DEFAULT: external-capable port, selection recorded in ADR at deadline].
Q7 USER POPULATION: personal single-user vs trusted team (guide assumes multi-user capable single install). Affects sharing emphasis + seed data, not architecture.
Q8 PLAN SCOPE: one plan, full Phases 0-7 [DEFAULT per guide definition-of-complete] vs stop at a phase boundary.
Q9 TEST STRATEGY: guide mandates contract-tests-first + deterministic fakes + agent-executed QA on every task [confirm].
Q10 UUID FORK (ch05): UUIDv4 pre-insert + PG18 uuidv7() DB-side [DEFAULT per TAD-011] vs adopt+lock RFC 9562 lib.
Q11 SEARXNG PROFILE: minimal (limiter off, no Valkey) [DEFAULT per guide] vs limiter on + Valkey.
Q12 OIDC/TRUSTED-PROXY: defer optional adapters [DEFAULT] vs include.
Q13 PROVISIONAL CAPS (browser recording, realtime voice, editable study aids): keep disabled behind flags [DEFAULT per guide].
Q14 NFR SEED SCALE: ch21 reference seed (25u/250nb/5k src/2M chunks/20k artifacts) as-is [DEFAULT].

## Decisions (with rationale)

- D1 (Q1, answered 2026-09-17; CORRECTED per Metis): Deployment target = THIS dev machine. Ryzen 5900HX 8C/16T, 64 GiB RAM, 2x Radeon VII 16 GiB HBM2 (gfx906), 1x RTX 3080 8 GiB, NVMe ~1000 MB/s. Host MEETS-OR-EXCEEDS the ch21 reference profile (8 cores/16GiB/500MB/s) — NFR gates run PINNED to the reference envelope (cgroup memory.max=16GiB, CPU quota=8, 1 API process + 2 worker slots; task 49). Disk budget communicated: ~250GB comfortable / ~500GB with full-seed NFR + local backups / ~150GB minimum. GPU note: gfx906 latest-ROCm-supported per D11; per-GPU backends pinned by on-host benchmarks.
- D2 (Q2, answered 2026-09-17; AMENDED per Metis): Model routing = local-first llama.cpp, external fallbacks Big Pickle then Muse Spark (order as user listed). Chat candidate Muse Glimmer 30B; EMBEDDING + RERANKER selections are part of this decision's ADR (multilingual DE/EN, benchmarked on locked corpus; reranker may be explicitly deferred with degraded=RRF-only). VERIFIED: Muse Spark = Meta closed-weight model on Meta Model API api.meta.ai/v1, OpenAI-compatible, 1M ctx, v1.3 2026-09-02; Standard tier does NOT train on data (use this), Contributor tier DOES (restricted class - FORBIDDEN). Big Pickle = OpenCode free-limited stealth model, external/bootstrap per baseline README:85-87, restricted/unknown privacy class + TIME-LIMITED availability ⇒ routing rule: Big Pickle lapse → route direct to Muse Spark Standard. All selections record the FULL PLANNING-HANDOFF:91 field set: license+supply-chain, version/digest, hardware/resource envelope, privacy classification, capability/quality benchmark, deterministic fake, degraded behavior, rollback.
- D3 (Q3, answered 2026-09-17; PINNED per Metis round-2): Reverse proxy/TLS = Caddy (guide-named default). Certificate procedure PINNED per plan task 8.2.1: Caddy internal/local CA for LAN hostnames (SAN recorded), ACME out-of-scope for v1; header stripping per ch04.
- D4 (Q4, answered 2026-09-17; hygiene-fixed per Metis): Backup = pgBackRest (PostgreSQL) + restic (blobs/config; target location RECORDED in ADR — local secondary path + documented offsite option), scripted to ch21 snapshot protocol (blob snapshot must include every object referenced by the consistent PG backup; GC safety delay > max backup window; manifest records DB recovery point, blob inventory root/hash, app/schema version, master-key recovery material location — never the key itself). Key-recovery procedure documented + drilled; RPO≤24h/RTO≤4h measured on the reference envelope (E2E-012 evidence).
- D5 (Q5+language, answered/amended 2026-09-17): OCR = Tesseract (isolated CLI, deu+eng traineddata). STT = whisper.cpp (GGML; device chosen by on-host benchmark: Vulkan-on-gfx906 vs CUDA-on-3080 vs CPU; fallback recorded), multilingual models. LANGUAGE PROFILE (user-amended): MULTILINGUAL MANDATORY - German + English at minimum. Feeds: PG FTS configs english+german (ch08 fallback only for languages beyond these; PG FTS ranking never labeled BM25), embedding + chat model selection ADRs must verify DE/EN quality, evaluation corpora include German judgments, chunker/language detection handles both, UI output-language settings preserved (reference parity).
- D6 (Q7, answered 2026-09-17; ACCEPTANCE REPHRASED per Metis): Users = you + small trusted team FROM DAY ONE. Acceptance = scripted multi-account E2E (owner/editor/viewer across 3+ real DB accounts, agent-executed) + ONE recorded manual operator drill with a real second account at the Phase-7 gate (ch25 runbook form). Sharing/collaboration (Phase 7) is real production scope; no live-human dependency at earlier gates.
- Model routing order stands uncorrected: local llama.cpp -> Big Pickle -> Muse Spark.
- D7 (Q11, answered 2026-09-17; Q-number recited per Metis): SearXNG = minimal profile (limiter OFF, no Valkey); application-side budgets/quotas per ch04/ch11. formats: [html, json] must be set explicitly (verified non-default).
- D8 (Q12, answered 2026-09-17): OIDC + trusted-proxy adapters DEFERRED for v1. Local accounts + Argon2id baseline. Ports remain, contract-tested via fakes only.
- D9 (Q6, RESOLVED 2026-09-17 with librarian verdict + user hardware knowledge; Q-number recited per Metis): LOCAL MEDIA CONFIRMED. TTS: Piper (or Kokoro-class) local, DE+EN. Images: SDXL-class on RTX 3080 CUDA. VIDEO (incl. Cinematic-capable tier): Wan 2.2 (Apache-2.0, clean license) = the video engine: TI2V-5B GGUF fits 8GB (Q8_0=5.4GB, Q4_K_M=3.43GB), 720p/24fps, T2V+I2V native, official <9min/5s-720p on 4090 -> est. 10-15min on 3080 (UNVERIFIED exact — prereq benchmark task 42.0 measures before first video task); I2V-A14B MoE via GGUF Q3/Q4_K_M + CPU offload to 64GB RAM = 480p/41f tier (tens of min/clip; acceptable per user). Multi-shot composition via storyboard+FFmpeg per ch14 architecture (RIFE/FILM interpolation + Real-ESRGAN upscale in recipe). ALL local media engines register through MOD-01 provider ports with capability descriptors — never a bespoke pipeline. Cinematic capability = ENABLED LOCALLY ⇒ FULL Phase-6 obligations (E2E-013 + MAN-003/010), benchmark-downgradable to disabled with recorded evidence, never silent. HunyuanVideo 1.5 = restricted-but-OK-private (Tencent community license, 100M MAU cap) as quality-fallback candidate; LTX-2.3 excluded by default (competing-product clause #20 + 22B exceeds 8GB envelope); CogVideoX excluded (registration + visit cap); Mochi 1 Apache-2.0 spare. Wan "2.7" does not exist as open weights (SEO fabrications) - use Wan 2.2 family.
- D11 (user correction 2026-09-17, supersedes librarian's gfx906 claim): gfx906 (Radeon VII) IS supported by the very latest ROCm - the "deprecated" verdict applied to older ROCm lines. Operator runs ROCm on these cards today (llama.cpp HIP). Consequences: (a) llama.cpp serving on VIIs = ROCm/HIP path (not just Vulkan); (b) VIIs MAY be usable for diffusion via ROCm PyTorch/ComfyUI - plan settles this EMPIRICALLY via a Phase-0/6 prerequisite-check + benchmark task on the actual host (per guide ch04 installer verification + ch23 selection benchmark), no web-claim assumption either way; (c) mixed-vendor 40GB unified diffusion pool remains impractical (PyTorch collectives have no cross-vendor mode - that finding stands), so orchestration per D10 assumes: 3080 = video CUDA, VIIs = llama.cpp/ROCm serving + possibly image diffusion once benchmarked.
- D10 (user-imposed 2026-09-17): LOCAL INFERENCE ORCHESTRATION IS MANDATORY. Machine VRAM (40GB aggregate, but chat 18-22GB + embeddings + reranker + whisper + SDXL + video cannot co-reside) means backend models/inference run SERIALLY/co-scheduled, not all-resident. The plan must include a local inference orchestrator: (a) owns GPU allocation policy per model (resident hot set = embeddings+reranker+chat by default; media/STT models cold-loaded on demand); (b) manages llama.cpp server + whisper.cpp + diffusion worker LIFECYCLE (load/unload with reference counting, single-flight loads, per-model concurrency where serial); (c) integrates with the guide's jobs capacity classes + waiting_capacity semantics so hour-long media generation cannot starve interactive chat - interactive text preempts or reserves; batch media jobs are preemptible/resumable; (d) capability health reflects model-load state (degraded-with-reason via /api/v1/capabilities per ch02/ch03 failure model). This extends MOD-01/MED-01 scope; no external orchestration service (K8s-style) - it is an in-app scheduler per TAD-005.

## Approval gate (historical record)
status: approved (2026-09-17, "go on then, looks good from here")
approach (as approved, corrected per review rr-02): One decision-complete work plan for the ENTIRE milpbookML v1.2 FINAL guide (Phases 0-7, all 22 workstreams, 61 capabilities, all 495 normative requirements each assigned to exactly one owner except declared shared cross-cutting records), structured as execution waves following the PLANNING-HANDOFF workstream DAG. Per-phase gate tasks (11/20/25/30/36/39/44/48) carry their own phase evidence at each phase exit; the final verification wave F1-F4 audits compliance/quality/manual-QA/scope after all 55 tasks; ch.25 release gates + ch.21 NFR gates + deploy/restore drills run in wave-8 tasks. Every task row (- [ ] N.) carries a 3-level micro-index (task.action.sub-step) enumerating every action/sub-step, each leaf mapped to ARCH-/TECH- requirement IDs (exact contiguous runs from .omo/research/registry-digest.md) and VER-*/test-path/evidence oracles from requirements.generated.json; master index appendix maps the full numbering tree to tasks. User process rules baked in: journal, git, MCP-before-bash (planner AND executor), max 2 delegates, delegation maximized.
default-confirmed items (accepted at approval): full Phase 0-7 scope in ONE plan; guide test regime (contract-first + deterministic fakes + agent-executed QA per task); UUIDv4 pre-insert + PG-side uuidv7() per TAD-011; provisional caps (realtime voice, recorded capture, evolving notes, editable study aids) stay disabled behind flags; late/optional caps (public notebooks, featured, analytics, connectors, starter artifacts) stay disabled; NFR seed at ch.21 reference scale; Big Pickle+Muse Spark as external fallbacks with disclosure; interactive audio advanced/provider-dependent (needs realtime duplex provider - default disabled unless local stack covers it).

## Review round state (review_required=true)
ROUND rr-milpbooklm-20260917-01: SUPERSEDED → round_status: inconclusive (both background tasks died mid-flight ~2026-09-17T18:0xZ, registry purged them: "Task not found" for bg_ec4fd699/bg_6916f5d6 and both session receipts ses_f4f8f33b4ffe2IKh2y6O62U7iG/ses_f4f8f32ffffeTy04R0LRgRWXVJ; no terminal verdicts. User ordered restart). No plan change occurred (sha256 re-verified ee96d26d before rr-02 init).

ROUND rr-milpbooklm-20260917-03 RESULTS (recorded 2026-09-17; USER HALT: "stop before running the high accuracy reviews" — no rr-04 dispatched):
- momus (ses_f4efbad6cffe8Y69kF0KJrXCqf, bg_071edcf8): result = changes_requested. 3 defects: (1) HIGH: phantom requirement IDs TECH-01-001/TECH-01-002 cited in task 1 (References L128 + Commit L131) and task 17 (References/Acceptance/Commit L272/273/275) — requirements.generated.json has NO TECH-01-* records (ch01 = ARCH-01-001..004 only); violates "never invent new oracles", poisons F1's 507-ID cross-check. Fix: remap to real IDs (module boundaries → ARCH-03-001..004/TECH-00-*; tool-free chat → ARCH-09-*/TECH-09-001) or mark as guide obligations outside ledger. (2) Blocks fields violate L118 "direct dependants only" in ~25 places (task-row Blocks stale — matrix was rebuilt rr-02 but task rows were NOT; false edges: T1→9, T3→12, T4→9, T5→13, T6→13/29, T8→20/25/30, T9 "all gates", T10→17, T13→15/21, T14→24/32, T15→17, T16→27, T17→18, T18→43, T31→35; omissions: T19,23,29,40,48 + matrix rows 1-10/12-18/21-23/26/31-34 gate dependants inconsistently listed). Authoritative Depends/Blocked-by side 100% consistent — no ordering hazard. Fix: mechanically regenerate every Blocks field from Depends. (3) LOW: L57 self-contradiction ARCH-05-001 owner (first clause "→task 3" vs shared-set "→ task 8"). Transcript: tool-output/tool_0b15efc80001iH8ak14ig9IwuR (verdict L929).
- independent oracle (ses_f4efbad5effercuHEjkJehc5kW, bg_d58baa97): result = changes_requested. 6 defects: (1) per-task Blocks stale ~25 tasks (same as momus 2, incl. undefined "all gates"); (2) matrix rows 26/33/34 omit gate dependants 30/36 that sibling rows list; (3) success criterion 3 (L635) unconditionally requires cinematic_video ENABLED — contradicts the benchmark-downgrade path (L15/L25/task 42): a legitimate downgrade makes criterion 3 unsatisfiable; (4) wave-8 label "(OPS-01b..f, 7)" — no OPS-01f exists (only b..e = 49-52); (5) stale "task 29/39 probes" in tasks 38/42 — 39 is a gate, 29 is the producer; (6) Caddy major version unpinned (only unpinned tool). Remediation effort per oracle: <1h mechanical. Transcript: tool-output/tool_0b15efc8c001kHElhgFzJ7UpLC (verdict L839).
- UNION FIX LIST for the next round (when resumed): momus#1 phantom TECH-01 remap; momus#2+oracle#1+oracle#2 full Blocks regeneration (all 55 task rows + matrix rows incl. consistent gate convention); momus#3 L57 first-clause align; oracle#3 success-criterion-3 downgrade-aware wording; oracle#4 wave-8 label "OPS-01b..e + release/docs tasks 53-55"; oracle#5 drop "/39"; oracle#6 pin Caddy v2 (verify current minor on-host or via REFERENCE-DEPENDENCIES discipline). Then re-hash plan, init rr-04, dispatch BOTH lanes fresh.
- State at halt: round_status rr-03 = active, lanes terminal (changes_requested), plan sha256 484036d5 (unchanged since rr-03 dispatch), working tree clean.

ROUND rr-milpbooklm-20260917-03: CLOSED → both lanes changes_requested (defect lists + union fix list recorded above). ALL rr-03 defects fixed (union list applied in full: TECH-01 phantom IDs remapped to ARCH-03/TECH-00/ARCH-09+ch01-obligation notes; ALL Blocks fields mechanically regenerated from the Depends column — 48 task rows + 27 matrix cells, gates annotated, verified spot-checks; L57 first clause aligned to task-8 owner; success criterion 3 downgrade-aware; wave-8 label corrected; both "29/39" refs cleaned; Caddy v2 major pinned). Plan sha256 moved 484036d5→3615e1cd. Both lanes resubmitted FRESH per the dual-review contract.

ROUND rr-milpbooklm-20260917-04 RESULTS (recorded 2026-09-17):
- momus (ses_f4e881bfcffep5FVdQfCETB09Z, bg_16165530): result = **approved** — VERDICT-APPROVED, ZERO defects ("no missing obligations, no ambiguous ownership, no unverifiable acceptance criteria, no contradictions"); two explicitly non-blocking traceability nits (task-3 ARCH-05-001 row-level reference; capability_registry 12-partial/12-rest descriptive split — F1 script is the declared resolver). Transcript: tool-output/tool_0b1c098bd001IK8rOK3sQgkEhz (verdict L601).
- independent oracle (ses_f4e881af2ffe0XtiMKcba0ntKF, bg_0008ffbe): result = changes_requested — ONE minor citation defect: plan L335 (task 24 References) pointed AD-015/016 at "baseline README" (grep count 0 there); definitions live in architecture-baseline/00-status-decisions.md (~L76/80). META-REQ-001 verified LEGITIMATE (ch25 test-group id, meta completeness oracle — not a phantom). All ~30 requirement ranges spot-checked: no phantoms. Blocks/DAG/counts/E2E/MAN/canonical labels/risk fences all verified sound. Transcript: tool-output/tool_0b1c098c6001QNDNgbntEq5fqH (verdict L914).
- Fix applied: L335 repointed to architecture-baseline/00-status-decisions.md AD-015/016. Plan sha256 moved 3615e1cd→5ba76bc0. Both lanes resubmitted FRESH (rr-05) per the dual-review contract (both must approve).

ROUND rr-milpbooklm-20260917-05 RESULTS (recorded 2026-09-18):
- momus (ses_f4e380101ffeylGvwWTx6nQAmm, bg_1c901adb): result = **approved** — VERDICT-APPROVED, ZERO defects. Full 638-line read; digest verified; rr-04→rr-05 sole delta (L335 AD-015/016 repoint) verified on disk (00-status-decisions.md L76/L80 exact). Clarity/verifiability/completeness all PASS.
- independent oracle (ses_f4e3800fbffeRV7UHPDbT9kEAo, bg_0028fb22): result = changes_requested — ONE defect cited, BUT byte-verification shows it is a FALSE POSITIVE (misquote): the defect claims plan L34 reads `E2E-006→24/4` and demands `E2E-006→24/14`; the artifact ACTUALLY reads `E2E-006→14/24 (refresh/version race)` (grep-verified, only occurrence; the only `24/4` on L34 belongs to the adjacent, correct `E2E-010→24/4`; L336 task-24 acceptance "w/ task 14" consistent; map ascending-order convention 5/18, 10/19, 13/20, 50/51 confirms 14/24 is the correct form). The oracle transposed the adjacent E2E-010 entry mid-analysis. Artifact ALREADY satisfies the recommendation's task set {14,24}. Everything else in the oracle's review verified clean: 55/55 matrix rows, DAG acyclic, JSON counts (507/495/12, 61 caps = 44+2+4+7+4, platform_core 61 canonical), tiers 155/166/170/4, E2E sweep 12/13 + MAN 10/10, PLANNING-HANDOFF:91 8-field record covered by six-field grouping ("defensible; I won't flag it"), AD-015/016 fix confirmed, L57 shared-set tail complete. Full transcript: tool-output/tool_0b1ef4167001EW0xbLjFWPnA75 (verdict L556, byte-exact, no trailing newline).
- Disposition: NO plan edit (applying a cosmetic reorder to satisfy a misquote would be dishonest and would invalidate momus's valid approval of this digest). Oracle lane CONTINUED IN-SESSION (same round rr-05, same launch-oracle-rr05-20260917T2350Z, artifact frozen at 5ba76bc0 — re-verified unchanged before dispatch) with a byte-level challenge: re-read L34, retract or sustain the defect with exact byte citations, restate final verdict. Momus approval remains valid (artifact unchanged).

```json
{
  "transition": "keep",
  "phase": "review_round_verdict_challenge",
  "applies_when": ["defect_citation_mismatch"],
  "atomic": true,
  "review_required": true,
  "plan_path": ".omo/plans/milpbookml-implementation.md",
  "plan_sha256": "5ba76bc0d8ed656ad0fcb15afba45429a874c714e6e9dcabaafeb0e8340612e5",
  "review_round_id": "rr-milpbooklm-20260917-05",
  "round_status": "active",
  "completion_cas": ["status=in_flight", "workspace_root", "runtime_home", "target", "launch_id", "round_id", "plan_sha256", "session", "receipt_identity=session", "live_plan_sha256=plan_sha256", "echoed_binding", "terminal_transition=in_flight->approved|changes_requested|inconclusive"],
  "pending-action": "oracle in-session re-verification of defect citation vs artifact bytes (same session ses_f4e3800fbffeRV7UHPDbT9kEAo, same launch identity, unchanged digest)",
  "review": {
    "momus": { "status": "approved", "workspace_root": "/home/srcds/dev/milpbookLM", "runtime_home": null, "target": ".omo/plans/milpbookml-implementation.md", "round_id": "rr-milpbooklm-20260917-05", "plan_sha256": "5ba76bc0d8ed656ad0fcb15afba45429a874c714e6e9dcabaafeb0e8340612e5", "launch_id": "launch-momus-rr05-20260917T2350Z", "session": "ses_f4e380101ffeylGvwWTx6nQAmm", "result": "VERDICT-APPROVED" },
    "independent": { "status": "in_flight_challenge", "workspace_root": "/home/srcds/dev/milpbookLM", "runtime_home": null, "target": ".omo/plans/milpbookml-implementation.md", "round_id": "rr-milpbooklm-20260917-05", "plan_sha256": "5ba76bc0d8ed656ad0fcb15afba45429a874c714e6e9dcabaafeb0e8340612e5", "launch_id": "launch-oracle-rr05-20260917T2350Z", "session": "ses_f4e3800fbffeRV7UHPDbT9kEAo", "result": "VERDICT-CHANGES-REQUESTED (1 defect — byte-verified FALSE-POSITIVE misquote; under challenge in-session)" }
  }
}
```
Metis iteration record: round 1 = 29 findings, all folded (commit c4bd749); round 2 = 29/29 ADDRESSED + 3 LOW new findings (N1 numbering-scheme text, N2 advanced-cap count, N3 stale draft sentences) — all fixed this commit; VERDICT: SATISFIED (session ses_f4fb2150affeqtztlT4548JZEZ).

ROUND rr-milpbookml-20260917-02 RESULTS (recorded 2026-09-17, both lanes completed with echoed binding + digest match):
- momus (ses_f4f5a257fffeUPa0oQUHbPyOc0): result = changes_requested. 4 defects: (1) E2E-006/007 ID swap vs spec (plan lines 34/424/439); (2) MAN runbook map mislabels 6/10 spec IDs — MAN-001=first-use source-to-citation (not backup drill), MAN-004=keyboard/screen-reader, MAN-005=responsive web (descriptions swapped), MAN-006=provider disclosure/policy (not citation viewer), MAN-007=long-running work+recovery (not browser compat), MAN-008=backup/restore drill (not install/upgrade); line 35 + task 54 line 600; (3) dependency matrix row 53 missing dep 54; (4) minor: workstream count 21→22. Transcript: tool-output/tool_0b0f9d115001CrCHS3guorFbPe (verdict line 654).
- independent oracle (ses_f4f5a2467ffe8ZokHpcgIVC8m6): result = changes_requested. 7 defects: (1) material: missing DAG edge 41→40 (41 consumes 40's media worker + Piper TTS adapter); (2) material: media_generation component orphaned from F1 coverage (tasks 40-43 cite no ARCH-14 IDs / Table A row); (3) material: "assigned exactly once" contradicts declared distribution + 9 unnamed-subset component splits; (4) matrix Blocks column mixes direct/transitive, incomplete; (5) MAN-007 owner 35/52 wrong; (6) digest Table D allocations stale vs canonical requirements.generated.json (ARCH-05-001, ARCH-14-001, ARCH-01-002..004; component totals platform_core 61/deployment 22/domain_model 21/capability_registry 9); (7) minors: "zero human intervention" header carve-out, deployment(23)+ARCH-05-001 double-count, "SSRD" typo. Transcript: tool-output/tool_0b0f9d1210016qzwUY6XRG7eBr (verdict line 815).
Fix policy: ALL cited issues fixed in plan+digest (see rr-03 init commit), then BOTH lanes resubmitted fresh per the dual-review contract.
