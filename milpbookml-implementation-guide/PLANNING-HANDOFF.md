# Implementation Planning Handoff

This is the entry point for the planning agent. It converts the architecture and technical chapters into an ordered, testable backlog without replacing either specification.

## Authority and precedence

When planning or resolving ambiguity, apply this order:

1. `architecture-baseline/00-status-decisions.md` and numbered architecture chapters define product behavior, safety and lifecycle invariants.
2. Numbered technical chapters and `00-status-decisions.md` define the reference implementation.
3. `capabilities.generated.json` defines applicability and phase ownership.
4. `requirements.generated.json` defines occurrence-level traceability and verification contracts.
5. This handoff defines sequencing and task shape.

A contradiction blocks the affected task and creates a specification issue; the planning agent does not silently choose a convenient interpretation. Historical reviews and changelogs are evidence, not normative sources.

## Planning output contract

Produce a plan containing epics, work packages and implementation tasks. Every task must include:

- task ID and one accountable workstream;
- capability IDs and requirement IDs;
- concrete deliverables and repository paths;
- prerequisites and downstream dependants;
- data/schema/API/event changes and migration/rollback needs;
- authorization, privacy, idempotency and failure behavior;
- fixtures plus positive, denial, failure and recovery tests;
- exact acceptance oracle and evidence path;
- execution tier and phase gate;
- decision or external dependency that can block it.

Do not create generic tasks such as “implement backend,” “add security,” or “write tests.” Split work until one task has one reviewable outcome and one coherent acceptance proof. Do not claim application code, migrations or tests already exist merely because this specification defines them.

## Workstream dependency graph

| ID | Workstream | Depends on | Completion evidence |
| --- | --- | --- | --- |
| `FND-01` | Repository, locks, module boundaries and CI | — | frozen installs, forbidden-import checks, unit/meta jobs |
| `FND-02` | Configuration, capability profile and specification tooling | `FND-01` | schema-valid profile, exact requirement census, drift-failing CI |
| `FND-03` | PostgreSQL roles, migrations and transaction conventions | `FND-01` | upgrade/rollback rehearsal against real PostgreSQL 18/pgvector |
| `FND-04` | Local identity, sessions, authorization and custody | `FND-03` | generated permission matrix plus denial/enumeration tests |
| `FND-05` | Jobs, leases, outbox, SSE and cancellation | `FND-03`, `FND-04` | crash/concurrency suite and browser resynchronization proof |
| `FND-06` | Immutable filesystem blobs and reconciliation | `FND-03` | crash-point tests, orphan reconciliation and integrity scan |
| `FND-07` | Telemetry, audit, secrets and security baseline | `FND-01`, `FND-04` | redaction tests, audit events, encrypted credential round trip |
| `MOD-01` | Provider contracts, registry, routing and fakes | `FND-02`, `FND-07` | provider contract suite and disclosure/policy denial cases |
| `ING-01` | Acquisition, source versions, canonical document and provenance | `FND-03`, `FND-05`, `FND-06` | text/PDF goldens, immutable activation and purge closure |
| `IDX-01` | Chunking, FTS, pgvector and rebuild lifecycle | `ING-01`, `MOD-01` | index parity/rebuild tests and locked retrieval corpus |
| `RAG-01` | Retrieval, grounding, citations and ordinary chat | `IDX-01`, `MOD-01`, `FND-04` | source-only answer/citation E2E and unsupported-claim rejection |
| `UI-01` | React shell, jobs, source viewer and accessibility | `FND-02`, `FND-04`, `FND-05` | Chromium/Firefox public-boundary flows and manual accessibility evidence |
| `ING-02` | Remaining document, image, audio, video and web ingestion | `ING-01`, `IDX-01` | hostile/golden corpus for every enabled source family |
| `RSR-01` | SearXNG discovery, safe fetch and Playwright browser tools | `FND-05`, `FND-07`, `MOD-01` | deterministic local-web research and SSRF/redirect denial suite |
| `EXE-01` | Bubblewrap broker and execution provider | `FND-05`, `FND-07`, `MOD-01` | escape/network/resource/output denial evidence on target host |
| `STD-01` | Artifact recipe/version/rendition framework | `FND-05`, `FND-06`, `RAG-01` | immutable manifest/provenance/export contract suite |
| `STD-02` | Notes, reports, Learning Overview, tables, maps and study aids | `STD-01`, `UI-01` | Phase 4 E2E, study-state isolation and export evidence |
| `STD-03` | Slides, infographics and document renderers | `STD-01`, `ING-02` | schema/render goldens plus perceptual/manual runbook |
| `MED-01` | Audio/Video Overviews and enabled realtime media | `STD-01`, `ING-02`, `MOD-01` | asynchronous recovery, A/V validation, captions and manual media evidence |
| `COL-01` | Sharing, copying, collaboration and optional publication | `FND-04`, `RAG-01`, `STD-01` | permission/copy/revocation E2E and dependency-restriction closure |
| `OPS-01` | Rootless deployment, upgrade, backup/restore, NFR and release | all applicable workstreams | production-equivalent install, restore, benchmark, SBOM and signed evidence bundle |
| `SCOPE-GUARD` | Deliberate non-target enforcement | `FND-02` | capability/profile meta-tests prove excluded features are not advertised or silently introduced |

The minimum critical path is `FND-01 -> FND-03 -> FND-05/FND-06 -> ING-01 -> IDX-01 -> RAG-01 -> STD-01`. `FND-02`, `FND-04`, `FND-07`, `MOD-01` and `UI-01` join before the Phase 1 gate; they are not cleanup work.

## Phase entry and exit gates

| Phase | Entry | Required exit |
| --- | --- | --- |
| 0 | host prerequisites known | rootless composition, locks, migrations, identity skeleton, jobs/outbox, blobs, capability/requirement meta-tests and deterministic fakes pass |
| 1 | Phase 0 evidence | one user-visible text/PDF-to-grounded-chat path, basic Source Guide, exact citations, source viewer and browser E2E pass |
| 2 | Phase 1 retrieval baseline | every enabled remaining source family has parser isolation, canonical/provenance goldens, refresh/rebuild/purge and retrieval evidence |
| 3 | safe transport and broker prerequisites | SearXNG/fetch/Playwright research plus Bubblewrap execution pass policy, SSRF, isolation and recovery gates |
| 4 | artifact core contract | notes, reports, Interactive Learning Overview, tables, maps, flashcards and quizzes pass provenance/export/study-state E2E |
| 5 | isolated renderer images | slides and infographics pass schema, revision, PDF/PPTX/PNG and manual perceptual gates |
| 6 | selected media capabilities | Audio/Video Overview modes pass capability negotiation, async recovery, provenance, safety, playback and manual A/V gates |
| 7 | stable private authorization | sharing/copy/collaboration gates pass; optional/provisional work ships only when explicitly enabled and fully tested |

No phase exits with placeholder adapters presented as implemented, unclassified requirements, unexplained `SHOULD` deviations, failed mandatory tests or stale evidence. Later work may be planned early, but it cannot force a dependency or abstraction into an earlier phase without a traced need.

## Decision deadlines

These are bounded implementation selections, not invitations to redesign the architecture:

| Decision | Deadline | Blocking effect |
| --- | --- | --- |
| local text-generation and embedding reference providers | before Phase 1 implementation acceptance | blocks quality/performance fixtures, not repository/fake-provider work |
| reverse proxy/TLS terminator and certificate procedure | before production-equivalent Phase 0 deployment evidence | blocks external deployment acceptance |
| backup/snapshot utility and key-recovery procedure | before first release candidate | blocks restore and release gates |
| OCR/STT engines and language profile | before affected Phase 2 tasks | blocks only their source capabilities |
| TTS/image/video providers and supported modes | before affected Phase 6 tasks | blocks only enabled media capabilities |
| BM25 or alternative lexical ranker | only after PostgreSQL FTS evaluation shows material benefit | never blocks baseline retrieval |

Each decision records license, version/digest, hardware/resource envelope, privacy class, benchmark, deterministic fake, degraded behavior and rollback.

## Backlog construction procedure

1. Import every stable/core capability for the phase and its `required_test_groups`.
2. Join all matching architecture and technical requirement records by capability/component.
3. Group by workstream and coherent deployable outcome, not by chapter alone.
4. Add schema/migration, authorization, lifecycle, telemetry, fixtures and documentation subtasks to the same outcome.
5. Place contract and failure tests before or alongside adapter implementation; place public-boundary E2E as soon as its dependencies exist.
6. Add manual cases only where the oracle is perceptual, accessibility-, hardware- or operator-dependent.
7. Record the exact phase-gate evidence produced by each task and reject orphan requirements or tests.
8. Run a scope check against `PARITY-SCOPE-AUDIT.md` before accepting the plan.

## Scope-control rules

- Stable/core capabilities in the current phase are required.
- Advanced/provider-dependent capabilities are required only when the selected provider profile claims them.
- Late/optional and provisional capabilities are excluded from the critical path unless the owner explicitly enables them.
- Deliberate non-targets never receive implementation tasks without a new architecture decision.
- Infrastructure or abstraction work needs at least one mapped requirement and near-term consumer. “Future scale” alone is not sufficient.
- Provider-neutral ports do not imply a plugin marketplace, dynamic code loading or a public SDK.
- Task equivalence to Gemini Notebook is the target; Google identity, proprietary storage, plan limits, visual cloning and cross-product integration are not.

## Definition of ready for implementation

A task is ready only when its requirements/capabilities, interfaces, data ownership, failure semantics, authorization, fixtures, oracle, dependency versions, migration/rollback, observability and evidence location are known. If a required selection has not reached its deadline, mark the task blocked; do not bury the choice inside implementation.

## Definition of phase-plan complete

The plan is complete when every applicable capability and normative requirement is assigned exactly once to an accountable task or cross-cutting gate; every task has explicit prerequisites and acceptance evidence; the dependency graph is acyclic; optional/provisional/non-target work is visibly separated; and the planned release path includes production-equivalent deployment, upgrade, restore, security, NFR and manual evidence.
