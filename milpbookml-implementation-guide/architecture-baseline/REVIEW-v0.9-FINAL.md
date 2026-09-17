# v0.9 FINAL — Superseded Historical Validation Record

This record is retained for audit history. v0.10 supersedes its Interactive Learning Overview classification after stable official Reports documentation became available. Use `REVIEW-v0.10-FINAL.md` for current validation.

> **Non-normative.** This file records the final architecture/package validation. If it conflicts with a numbered chapter, the numbered chapter and `00-status-decisions.md` are authoritative.

**Validation date:** 16 September 2026  
**Package status:** architecture-complete / ready for a separate technical specification  
**Scope:** factual correctness, cross-chapter consistency, lifecycle/security closure, missing interfaces, feature creep and package integrity.

## 1. Final corrections incorporated

The final package includes the post-v0.5 corrections rather than leaving them as review comments:

- PostgreSQL native FTS is described as lexical/full-text retrieval, not BM25; BM25 remains an optional retrieval-adapter implementation.
- Google's September 2026 study announcement is covered completely without promoting rollout claims to stable parity: Interactive Learning Overviews, general realtime notebook voice, mobile audio recording, editable/new quiz formats and performance-aware study follow-up are all tracked as provisional over reusable architecture primitives.
- `StudySessionSnapshot` closes the privacy/reproducibility gap for chat follow-up over mutable, per-user flashcard/quiz results.
- Very short sources use an explicit document/root-level citation fallback rather than fabricated span coordinates.
- Slide-deck parity now includes length controls, feedback and the documented edit/delete/restore/reorder/export behaviors; source-aware revisions are recorded as an intentional improvement over the reference product's current source-blind revision limitation.
- The dependency roadmap is a DAG: the model capability plane feeds embeddings/knowledge and reasoning instead of incorrectly appearing after the knowledge layer.
- The NFR benchmark and restore targets now name concrete hardware, fixture, concurrency and storage-envelope conditions, so the published numbers are actually reproducible.
- Big Pickle claims now use the current Zen documentation only: free/limited-time stealth status, OpenAI-compatible chat-completions surface and training/improvement caveat; uncertain unauthenticated-endpoint behavior is no longer asserted.
- Hard/privacy purge traverses the complete known content-bearing dependency graph, including derived notes, artifacts/renders, run evidence, research/tool/execution outputs, generated files, prompt/context snapshots, staged execution inputs and caches.
- Source/connector restrictions propagate through derived outputs and are re-evaluated at every applicable exposure boundary.
- Account disablement is immediate even for a sole owner; ownership resolution uses locked custody plus an audited metadata-only operation that does not grant notebook-content access.
- PostgreSQL/blob storage uses an explicit crash-consistent finalize/reference/reconciliation/deletion contract.
- Risky/native parser/OCR/converter/media processing is isolated from the main application with no ambient secrets/network and bounded resources.
- Trusted reverse-proxy authentication has an explicit non-bypassable trust boundary.
- Retryable mutation commands have client idempotency semantics; stream disconnect/reconnect and durable-job resynchronization are defined.
- Reference NFRs are measurable while remaining appropriate for a small self-hosted deployment.
- Every normative requirement must be classified in a requirements-to-tests ledger before implementation/release; an implementation agent cannot treat code execution or line coverage as proof of behavior.
- The test strategy now defines deterministic production-boundary fixtures, thirteen canonical automated E2E journeys, manual/perceptual release scenarios, browser/CI tiers, AI-quality oracles, flake/quarantine rules and retained evidence.
- Technical-specification and feature definitions of done now require interfaces, schemas/migrations, policy boundaries, observability, failure/idempotency behavior, fixtures and mapped automated/manual acceptance tests.
- Normative requirement extraction is case-insensitive and every recommendation is implemented or has a reviewed deviation; lowercase wording cannot escape traceability.
- AD-026 capability/conformance profiles make phased, optional, provisional and non-target applicability explicit and prohibit invalid `N/A` results.
- Multimodal architecture covers synchronous/asynchronous providers, idempotent remote-operation reconciliation, callback security, untrusted media validation, stage recovery, safety/refusals, renditions/seekable delivery and dedicated video test evidence.
- Stable parity details now explicitly include local source-title editing, study-viewer navigation/fullscreen controls and detached non-synchronizing exports.

## 2. External facts rechecked

The following time-sensitive claims were rechecked against current public documentation during finalization:

- PostgreSQL built-in full-text ranking exposes `ts_rank` / `ts_rank_cd`; the architecture does not call this BM25.
  - https://www.postgresql.org/docs/current/textsearch-controls.html
- Bubblewrap versions before 0.12.0 are affected by GHSA-pxhw-h44j-8pfx; 0.12.0 contains the fix and removes setuid-build support.
  - https://github.com/containers/bubblewrap/security/advisories/GHSA-pxhw-h44j-8pfx
  - https://github.com/containers/bubblewrap/releases/tag/v0.12.0
- OpenCode currently lists Big Pickle as a limited-time free model and states that data collected during its free period may be used to improve the model.
  - https://opencode.ai/docs/zen
- Current stable Gemini Notebook help documents the existing Studio/report families used by the parity baseline. The newly announced Learning Overview is being rolled out and is therefore non-normative in this snapshot until stable help documentation catches up.
  - https://support.google.com/gemininotebook/answer/16206563
- Current help continues to document source-only ordinary chat, private per-user chat history, user-selected sources, notes workflows, the supported source families, current Studio artifacts and notebook-copy exclusions used by the parity matrix.
  - https://support.google.com/gemininotebook/answer/16179559
  - https://support.google.com/gemininotebook/answer/16215270
  - https://support.google.com/gemininotebook/answer/16262519
- Google's 15 September 2026 announcement documents general realtime notebook voice, mobile recording, Interactive Learning Overviews, additional/editable quiz formats and study-performance follow-up as upcoming/rolling out.
  - https://blog.google/innovation-and-ai/products/gemini-notebook/new-study-tools-september-2026/
- Current OpenCode Zen documentation lists Big Pickle as a free limited-time stealth model, exposes `big-pickle` on an OpenAI-compatible chat-completions endpoint and warns that collected free-period data may be used for model improvement.
  - https://opencode.ai/docs/zen

External-reference claims are snapshots, not architectural dependencies. Provider/product changes do not alter the domain model.

## 3. Scope/bloat check

The final baseline does **not** require Kubernetes, Kafka, Redis, Elasticsearch/OpenSearch, a standalone vector database, MinIO, a knowledge graph, a public plugin marketplace/SDK, an organization/workspace tenancy hierarchy, a native mobile client, or vendor identity/storage APIs.

The retained complexity is tied to existing requirements: provenance/versioning, authorization, privacy purge, durable asynchronous jobs, controlled external providers, untrusted-file parsing, research tools and isolated code execution.

## 4. Package validation criteria

Final release validation checks:

- all Markdown-relative links resolve;
- Markdown fences are balanced;
- chapter numbering and README chapter links match;
- ADR references resolve and `AD-001` through `AD-026` are present exactly once in the authoritative decision ledger;
- no stale superseded package-status/review reference remains outside changelog history;
- no PostgreSQL-native ranking path is mislabeled as BM25;
- announced September 2026 study/voice features are not listed as stable release gates;
- manifest checksums match every packaged specification file;
- no duplicate/stale long-form audit file remains;
- Chapter 25 contains stable traceability/test-case contracts, `E2E-001` through `E2E-013`, `MAN-001` through `MAN-010` (with conditional `MAN-009`), capability-driven applicability, CI tiers and implementation definition-of-done requirements.

## 5. Handoff status

No architecture-blocking open question remains. Deferred items in Chapter 23 are implementation selections to be benchmarked/configured without changing the domain or subsystem boundaries. The technical specification must make those concrete selections and satisfy Chapter 25's traceability and evidence contract. Any future choice that violates the provider/provenance/policy interfaces or introduces a new architectural dependency requires a new ADR rather than being smuggled in as an implementation detail.
