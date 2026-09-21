# Decisions — milpbooklm-implementation

Architectural choices and rationales discovered during work on this plan.

_Auto-scaffolded by /start-work. Append new entries below - never overwrite._

---

## D12 (2026-09-18, user) — Prototype-first execution + tooling mandates
- **Prototype-first**: all test-writing and non-prototype work is POSTPONED to a second wave. Wave 1 (current) delivers a working first prototype with most functionality. Manual/hands-on QA by agents is explicitly NOT deferred.
- **MCP-tools-first** (permission-enforced): every subagent prompt must name serena (find_symbol, get_symbols_overview, find_referencing_symbols, replace_symbol_body, execute_shell_command), codegraph, tldr, lsp_diagnostics, glob/grep/read as the primary tools; bash LAST resort; one-off scripts forbidden.
- **Concurrency**: max ONE active delegated agent at a time (user, 2026-09-18 later: supersedes the earlier "two as before").
- Task completion during prototype wave = functionality demonstrably works (hands-on evidence) + existing pipeline stays green; VER-evidence batches/mutation QA/new test files = second wave.

## D13 (2026-09-19, user) — Light-QA mode + dispatch gating
- Workers were doing extensive multi-scenario QA batteries (30-assertion drivers, SIGKILL drills, long transcripts). STOP mandating these.
- Permitted for workers: **brief manual smoke** (does the core flow work when run by the agent?) + **linting** (ruff/mypy/import-linter + existing test suite green).
- NOT requested anymore: multi-scenario QA drivers, fault-injection drills, long QA transcripts, heavy verification packs. Evidence JSON stays minimal (commands, exits, deferred list).
- Deep QA/evidence batteries = wave 2.
- **Dispatch gating**: orchestrator STOPS after each agent finishes; next dispatch only on explicit user instruction.

## D14 (2026-09-20, user) — Embeddings on CPU for the prototype
- bge-m3 (Q8_0, ~600 MB) served by llama.cpp in embedding mode on CPU. Query-side latency (~0.1–0.5 s) acceptable; bulk ingestion indexing slower but it is a background job. Keeps both GPUs dedicated to chat. Escalation path if too slow: second Radeon VII (config-only; T10 orchestrator models hot/cold workloads) or fallback model multilingual-e5-small (~120M, quality hit). Final call = quick benchmark at T15, not pre-guessed.

## D15 (2026-09-20, user) — Direct-route execution; gating relaxed
- The direct route to the functional prototype = T11 (ultra-light gate) → T12 → T13 → T14 → T15 → T16 → T17 → T18, sequential. Testable checkpoints: CP1 upload→canonical text (after T13), CP2 search (after T15), CP3 grounded chat with citations (after T17), CP4 browser UI (after T18).
- Prototype trims: T14 v1-only provenance (no refresh flows); T17 notebook extras minimal; T18 no E2E harness / full a11y battery (wave 2); T19/T20 after the prototype exists.
- D13's dispatch gating is SUPERSEDED by the user's 2026-09-20 directive to adjust execution to the mapped route and keep going ("did you map the direct route ... and adjust our execution accordingly?" — boulder continuation directives concur). One delegated agent at a time still applies.
- Artifact-path spelling unification (milpbookml → milpbooklm) commissioned 2026-09-20; canonical project spelling is `milpbooklm` in-repo, directory stays `milpbookLM`.


## D16 (2026-09-21, user) — No new model acquisitions; local chat = prod llama.cpp config
- User order when T19 tried to download "Muse Glimmer-30B": "just use the prod config with what we already have!"
- Local chat selection (MOD-01b slot a) = **Swift-Qwen3.8-27B-Q6_K** served by `/home/srcds/dev/uf3_rocm6.1_llama.cpp/swift_llama_start-q6_f16_f16.sh` on 2×RadeonVII gfx906 (DFlash2 + ngram-mod spec decode, `-ts 35,20,45 -sm layer`, f16/f16 KV, port 8009). Supersedes plan line 287 "Muse Glimmer-30B Q4/Q5"; the T19 ADR records this substitution.
- NO GGUF downloads without explicit user order; disk at 97% (34GB free) independently forbids it.
- On-host benchmark evidence = light live probes of the running :8009 (it IS the selected deployment) + the perf journal in the prod script header (E82/E83 lane: pp16384 ~369 / fill120k ~327 / TG ~13.3 t/s). No second model load; GPUs stay owned by the serving instance.

## D17 (2026-09-21, task 19) — MOD-01b reference selections
- Local chat is Swift-Qwen3.8-27B-Q6_K through the D16 production llama.cpp deployment; the prior Glimmer candidate is rejected for this installation.
- Local embeddings are bge-m3 Q8_0, CPU-only, dimension 1024. A dedicated reranker is explicitly deferred; degraded/selected prototype behavior is RRF-only fusion.
- Checked-in fallback order is local llama.cpp → Big Pickle → Muse Spark Standard. Big Pickle lapse/restriction skips directly to Muse Spark Standard; all external dispatch remains disclosure-, policy-, and credential-gated.
- Credential-free probes left the effective runtime route local-only: Big Pickle direct chat returned HTTP 403 (OpenCode-client restriction); Muse Spark Standard returned HTTP 401 (no credential).
