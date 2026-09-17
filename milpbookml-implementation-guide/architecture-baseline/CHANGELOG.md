# Specification Changelog

## v0.10 FINAL — 2026-09-16

- Promoted Interactive Learning Overview to stable Phase 4 parity after the official Reports help page documented interactive reports, the Learning Overview template and embedded Studio artifacts.
- Kept general realtime notebook voice, browser-equivalent recording, evolving note-context semantics, editable/new quiz types and study-performance chat follow-up provisional because stable feature documentation has not established all announced behavior.
- Added a planning-handoff audit without changing the architecture's self-hosting, provider-neutrality, security, provenance or anti-bloat boundaries.

## v0.9 FINAL — 2026-09-16

This is the architecture-closure release after three validation passes over v0.8. It does not begin the separate implementation technical specification.

### Requirements and conformance closure

- Made normative extraction case-insensitive within numbered chapters and required classification of every `MUST`/`MUST NOT`/`SHOULD`/`SHOULD NOT`; an unimplemented `SHOULD` now requires an explicit reviewed deviation.
- Added AD-026 and a machine-readable capability/conformance profile for each phase/release. Stable/core or enabled behavior cannot be marked `N/A`; enabling optional functionality activates its functional, security, privacy, lifecycle and manual tests.
- Corrected the golden-fixture contract to cover every Chapter 02 source family and acquisition behavior rather than an incomplete representative subsection.
- Made stable parity details explicit: editable local source titles without content mutation, previous/next/full-screen flashcard and quiz controls, and detached export snapshots whose external copies cannot be synchronized or revoked by later application ACL changes.

### Multimodal and video closure

- Expanded media capability descriptors with formats/codecs/containers, resolution/aspect/duration, languages/voices, asset limits, async/cancel/revision behavior, safety/refusal, retention and provenance metadata.
- Added a normalized remote media-operation contract for submit, idempotency, polling/authenticated callbacks, cancellation, expiry, refusal, result acquisition and uncertain-outcome reconciliation without duplicate billable submissions.
- Added staged media checkpoint/recovery semantics and explicit user distinction between reconciling existing work and starting a new charged generation.
- Required untrusted-binary validation, isolated probing/transcoding/composition, original-versus-derived rendition provenance, browser-compatible transcodes, thumbnails/posters, captions/transcripts and purge/GC traversal.
- Added explicit media safety/refusal policy, preservation of provider safety/content-credential metadata and a rule forbidding fallback merely to evade safety policy.
- Required seekable authorized delivery through byte ranges or equivalent and technical-spec selection of baseline browser codecs/containers.
- Added multimodal quality metrics, fake async media providers and hostile/corrupt media fixtures, `E2E-013`, and manual source-grounded video quality validation.

### Official-reference reconciliation

- Rechecked current official Gemini Notebook documentation for chat, sources, notes, Studio artifacts, study aids, infographics, slides, audio/video and sharing. The stable/provisional/deliberate-divergence classifications remain correct.

## v0.8 FINAL — 2026-09-16

This release closes the implementation-verification gap found after v0.7. Product scope and the Gemini Notebook parity baseline are unchanged.

### Agent-executable testing and technical-specification handoff

- Added a mandatory requirements-to-tests traceability ledger: every normative requirement receives a stable id and maps to an automated test, manual test, documented analysis or explicit approved deferral.
- Defined a required test-case form with purpose/risk, fixtures, exact actions, observable oracle, forbidden side effects, tolerance, cleanup and retained evidence.
- Specified a deterministic reference harness: production-schema PostgreSQL/blob integration, entity factories, controllable time/ids/failure injection, fake model/embedding/connector/search services, hostile source fixtures, production Bubblewrap-policy tests and real-browser automation.
- Added twelve canonical automated E2E journeys covering source-to-citation, heterogeneous retrieval, Studio artifacts, notes, sharing/copy, refresh races, study privacy, agentic code/research, reconnect/cancellation, purge/account lifecycle, provider policy/disclosure and upgrade/recovery.
- Added a mandatory manual release runbook for source/citation usability, audio, rendered media/artifacts, accessibility, responsive web behavior, external-provider disclosure, long-running job recovery and operator-led restore; provisional realtime voice gains a conditional hardware/manual scenario when enabled.
- Defined browser support, pre-commit/PR/nightly/release/security execution tiers, evidence retention, live-provider isolation, nondeterminism/statistical evaluation rules and a strict flaky-test/quarantine policy.
- Required risk-focused property/fuzz/mutation testing where useful and prohibited coverage percentages or mass snapshot updates from standing in for meaningful assertions.
- Added the implementation definition of done: interfaces, schemas/migrations, policy, observability, failure/idempotency semantics, fixtures and mapped automated/manual acceptance tests must exist before a subsystem is implementation-ready.

### Final verification

- Rechecked current official Gemini Notebook help for ordinary source-grounded chat, sources, notes, Studio families, flashcards/quizzes, slide decks, Audio/Video Overviews, sharing/copy behavior and the September 2026 rollout announcement. No v0.7 parity classification required correction.
- Added an evaluation release protocol with versioned development/held-out corpora, fixed pre-release thresholds, baseline comparisons, exact deterministic invariants, statistical evidence and human-adjudication rules.

## v0.7 FINAL — 2026-09-16

This release is the full post-v0.6 parity/factual audit against current official Gemini Notebook and upstream documentation.

### Reference-product corrections and omissions closed

- Added every material item in Google's 15 September study-tools announcement as **provisional/announced**, not stable parity: general realtime notebook voice chat, browser-equivalent recorded-audio capture, Interactive Learning Overviews, additional/editable quiz formats and study-performance chat follow-up.
- Added immutable user-private `StudySessionSnapshot` context so performance follow-up cannot leak another collaborator's answers or change mid-generation.
- Completed stable slide-deck parity with short/default/long length, feedback, zoom, edit/delete/restore/reorder and PDF/PPTX behavior; recorded source-aware revision as an intentional improvement over the reference product's current limitation.
- Added the documented short-source citation fallback, notebook emoji metadata, specific note transformations, media viewer controls and share-link revocation semantics.
- Explicitly separated general realtime notebook voice chat from Interactive Audio Overview and recorded native mobile/share-sheet/offline behavior as a deliberate non-target.

### Architecture and factual corrections

- Replaced the misleading linear dependency ladder with a DAG in which the model capability plane feeds both embeddings/knowledge and reasoning.
- Defined the previously missing NFR reference test profile and backup/restore data envelope, making the latency/RPO/RTO targets reproducible rather than nominal.
- Removed an insufficiently supported claim that OpenCode's free chat surface currently requires no Authorization header. Big Pickle is now described only with current official Zen facts: free limited-time stealth status, OpenAI-compatible chat-completions endpoint and the model-improvement data caveat.
- Added regression tests for study-context privacy, short-source citations, share-link revocation and the concrete performance/restore profile.

## v0.6 FINAL — 2026-09-16

This release closes the issues found in the post-v0.5 architecture review without adding new product/infrastructure scope.

### Correctness and lifecycle closure

- Corrected retrieval terminology: the reference deployment uses PostgreSQL **lexical/full-text search**, whose native `ts_rank`/`ts_rank_cd` ranking is not BM25. BM25 remains an optional replaceable lexical ranker behind the retrieval interface if evaluation demonstrates a benefit.
- Reclassified the newly announced **Learning Overview** / interactive-report experience as provisional/non-normative until stable product documentation confirms shipped behavior. The generic composite-artifact substrate remains because it is useful independently and can implement the feature later without redesign.
- Expanded AD-016 hard/privacy purge into an explicit complete known content-bearing dependency traversal covering source-derived/provenance-linked `NoteRevision`s, `ArtifactVersion`s/renders, `RunEvidenceSnapshot`s, research/tool/execution outputs, generated files, staged execution inputs, stored prompt/conversation/context snapshots and caches.
- Added AD-023: source/connector access and reuse restrictions propagate through derived content and are re-evaluated at read/view, notebook-copy, share-link, download/export and publication boundaries. Generation is not permission laundering.
- Fixed account-disable/ownership semantics in AD-022: disablement is immediate; sole-owner notebooks enter locked administrative custody; an audited metadata-only admin operation may transfer ownership or schedule deletion without granting notebook-content access.
- Added AD-024 crash-consistent blob lifecycle for PostgreSQL + filesystem/object storage: temporary write, hash/size validation, immutable finalization, DB reference commit, orphan reconciliation, and reference-aware two-phase deletion.

### Security and API closure

- Made OS-process isolation mandatory for risky/native document parsers, OCR/conversion/archive/media tools processing untrusted bytes, with no ambient secrets/network, restricted workspace and explicit resource/time limits.
- Defined the trusted reverse-proxy authentication boundary: only configured proxy peers can assert identity, client headers are stripped/ignored, and direct backend bypass is forbidden.
- Added browser/API command idempotency for retryable mutating commands, plus explicit disconnect/reconnect semantics for streamed generation and durable job/event streams.
- Strengthened regression tests for purge closure, derived-source restrictions, parser isolation, proxy-header spoofing/bypass, sole-owner custody, blob crash consistency, command retries and stream reconnects.

### Minimal measurable NFR baseline

- Added reference acceptance targets rather than vague “fast/reliable/accessibility” language: p95 <= 500 ms for ordinary non-model API operations on the documented reference profile, p95 <= 2 s job-state visibility, WCAG 2.2 AA for primary web workflows, and reference single-host disaster recovery of RPO <= 24 h / RTO <= 4 h within the published test envelope.
- Added blob checksum/integrity reconciliation requirements and measurable durable-job orphan recovery semantics.

### Scope/bloat cleanup

- Replaced the long duplicated v0.5 handoff review with a concise non-normative validation record.
- Kept the baseline infrastructure deliberately small: PostgreSQL + FTS + `pgvector` + PostgreSQL-backed jobs/outbox + local-filesystem blob backend. No Kafka, Elasticsearch/OpenSearch, separate vector DB, MinIO, Kubernetes, knowledge graph, plugin marketplace or native mobile client was added.
- Kept `00-status-decisions.md` as the authoritative cross-cutting decision ledger and reduced duplicate normative wording elsewhere to references/implementation contracts.

## v0.5 — superseded baseline — 2026-09-16

v0.5 established the major architecture: self-hosted GNU/Linux multi-user deployment, provider-neutral/local-first model routing, immutable source/canonical/provenance model, ordinary grounded chat versus explicit Agentic Chat, generic Studio artifacts, Bubblewrap-based execution, PostgreSQL-centric persistence/jobs, local-account authentication, source refresh/versioning, asynchronous authorization revalidation and removal-versus-purge semantics.

The v0.6 review found and corrected several closure/terminology issues in that baseline, most importantly PostgreSQL FTS/BM25 terminology, Learning Overview rollout status, purge completeness, derived-source restriction propagation, sole-owner disablement, DB/blob crash consistency, parser isolation and API retry/reconnect semantics.
