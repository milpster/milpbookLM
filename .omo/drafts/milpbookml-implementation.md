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

- D1 (Q1, answered 2026-09-17): Deployment target = THIS dev machine. Ryzen 5900HX 8C/16T, 64 GiB RAM, 2x Radeon VII 16 GiB HBM2 (gfx906), 1x RTX 3080 8 GiB, NVMe ~1000 MB/s. Meets ch21 NFR reference profile exactly (8 cores/16GiB/500MB/s) - all NFR gates testable on-host. Disk budget communicated: ~250GB comfortable / ~500GB with full-seed NFR + local backups / ~150GB minimum. GPU note: gfx906 = llama.cpp Vulkan (ROCm-deprecated), 3080 = CUDA; model-serving ADR pins per-GPU backends.
- D2 (Q2, answered 2026-09-17): Model routing = local-first llama.cpp, external fallbacks Big Pickle then Muse Spark (order as user listed). VERIFIED: Muse Spark = Meta closed-weight model on Meta Model API api.meta.ai/v1, OpenAI-compatible, 1M ctx, v1.3 2026-09-02; Standard tier does NOT train on data (use this), Contributor tier DOES (restricted privacy class - excluded by default). Muse Glimmer 30B (Apache-2.0 open weights, llama.cpp-targeted) = recommended local chat-model candidate (~18-22GB Q4/Q5 fits 40GB aggregate VRAM). Big Pickle = OpenCode free-limited stealth model, external/bootstrap per baseline README:85-87, data-use caveat. All three need the guide's selection record (license/digest/benchmark/fake/privacy/fallback/rollback) at the Phase-1 ADR task; deterministic fakes for CI regardless.
- D3 (Q3, answered 2026-09-17): Reverse proxy/TLS = Caddy (guide-named default). Certificate procedure: Caddy auto-TLS with internal/local-CA or ACME depending on exposure - folded into OPS-01/FND tasks; header stripping per ch04.
- D4 (Q4, answered 2026-09-17): Backup = pgBackRest (PostgreSQL) + restic (blobs/config), scripted to ch21 snapshot protocol (blob snapshot must include every object referenced by the consistent PG backup; GC safety delay > max backup window; manifest records DB recovery point, blob inventory root/hash, app/schema version, master-key recovery material location). Key-recovery procedure documented + drilled. Key-recovery procedure documented + drilled.
- D5 (Q5+language, answered/amended 2026-09-17): OCR = Tesseract (isolated CLI, deu+eng traineddata). STT = whisper.cpp (GGML; Vulkan on Radeon VIIs), multilingual models. LANGUAGE PROFILE (user-amended): MULTILINGUAL MANDATORY - German + English at minimum. Feeds: PG FTS configs english+german (ch08 fallback only for languages beyond these), embedding + chat model selection ADRs must verify DE/EN quality, evaluation corpora include German judgments, chunker/language detection handles both, UI output-language settings preserved (reference parity).
- D6 (Q6, answered 2026-09-17): Users = you + small trusted team FROM DAY ONE. Implications: multi-user flows exercised with real second users during phase gates (not fixtures-only); sharing/collaboration (Phase 7) is real production scope; team seeding + role matrix (owner/editor/viewer) tested with actual accounts in E2E + manual drills.
- Model routing order stands uncorrected: local llama.cpp -> Big Pickle -> Muse Spark.
- D7 (Q8, answered 2026-09-17): SearXNG = minimal profile (limiter OFF, no Valkey); application-side budgets/quotas per ch04/ch11. formats: [html, json] must be set explicitly (verified non-default).
- D8 (Q9, answered 2026-09-17): OIDC + trusted-proxy adapters DEFERRED for v1. Local accounts + Argon2id baseline. Ports remain, contract-tested via fakes only.
- D9 (Q7, RESOLVED 2026-09-17 with librarian verdict + user hardware knowledge): LOCAL MEDIA CONFIRMED. TTS: Piper (or Kokoro-class) local, DE+EN. Images: SDXL-class on RTX 3080 CUDA. VIDEO (incl. Cinematic-capable tier): Wan 2.2 (Apache-2.0, clean license) = the video engine: TI2V-5B GGUF fits 8GB (Q8_0=5.4GB, Q4_K_M=3.43GB), 720p/24fps, T2V+I2V native, official <9min/5s-720p on 4090 -> est. 10-15min on 3080 (UNVERIFIED exact); I2V-A14B MoE via GGUF Q3/Q4_K_M + CPU offload to 64GB RAM = 480p/41f tier (tens of min/clip; acceptable per user). Multi-shot composition via storyboard+FFmpeg per ch14 architecture (RIFE/FILM interpolation + Real-ESRGAN upscale in recipe). Cinematic capability = ENABLED LOCALLY (marginal-but-real; honest conformance descriptor records resolution/duration envelope). HunyuanVideo 1.5 = restricted-but-OK-private (Tencent community license, 100M MAU cap) as quality-fallback candidate; LTX-2.3 excluded by default (competing-product clause #20 + 22B exceeds 8GB envelope); CogVideoX excluded (registration + visit cap); Mochi 1 Apache-2.0 spare. Wan "2.7" does not exist as open weights (SEO fabrications) - use Wan 2.2 family.
- D11 (user correction 2026-09-17, supersedes librarian's gfx906 claim): gfx906 (Radeon VII) IS supported by the very latest ROCm - the "deprecated" verdict applied to older ROCm lines. Operator runs ROCm on these cards today (llama.cpp HIP). Consequences: (a) llama.cpp serving on VIIs = ROCm/HIP path (not just Vulkan); (b) VIIs MAY be usable for diffusion via ROCm PyTorch/ComfyUI - plan settles this EMPIRICALLY via a Phase-0/6 prerequisite-check + benchmark task on the actual host (per guide ch04 installer verification + ch23 selection benchmark), no web-claim assumption either way; (c) mixed-vendor 40GB unified diffusion pool remains impractical (PyTorch collectives have no cross-vendor mode - that finding stands), so orchestration per D10 assumes: 3080 = video CUDA, VIIs = llama.cpp/ROCm serving + possibly image diffusion once benchmarked.
- D10 (user-imposed 2026-09-17): LOCAL INFERENCE ORCHESTRATION IS MANDATORY. Machine VRAM (40GB aggregate, but chat 18-22GB + embeddings + reranker + whisper + SDXL + video cannot co-reside) means backend models/inference run SERIALLY/co-scheduled, not all-resident. The plan must include a local inference orchestrator: (a) owns GPU allocation policy per model (resident hot set = embeddings+reranker+chat by default; media/STT models cold-loaded on demand); (b) manages llama.cpp server + whisper.cpp + diffusion worker LIFECYCLE (load/unload with reference counting, single-flight loads, per-model concurrency where serial); (c) integrates with the guide's jobs capacity classes + waiting_capacity semantics so hour-long media generation cannot starve interactive chat - interactive text preempts or reserves; batch media jobs are preemptible/resumable; (d) capability health reflects model-load state (degraded-with-reason via /api/v1/capabilities per ch02/ch03 failure model). This extends MOD-01/MED-01 scope; no external orchestration service (K8s-style) - it is an in-app scheduler per TAD-005.

## Approval gate
status: drafting
<!-- When exploration is exhausted and unknowns are answered, set status: awaiting-approval. -->
<!-- That durable record is the loop guard: on a later turn read it and resume at the gate instead of re-running exploration. -->
