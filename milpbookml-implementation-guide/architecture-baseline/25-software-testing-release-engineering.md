# 25 — Software Testing, Release Engineering and Supply Chain

## 1. Purpose

AI evaluation answers whether retrieval/generation quality improved. Software testing answers whether the system is correct, secure and deployable. Both are mandatory and must remain separate concerns.

## 2. Test layers

The project MUST maintain:

- unit tests for domain logic, parsers, policy/routing and artifact recipes;
- golden-file tests for canonical-document parsing and provenance coordinates;
- integration tests covering DB, object store, indexes, queues and authorization;
- provider-contract tests using deterministic mock servers/fixtures;
- multimodal-provider/renderer contract tests covering synchronous and remote-asynchronous media operations, capability negotiation, idempotent polling/callback reconciliation, cancellation/refusal, binary validation/transcoding and derived-rendition lifecycle;
- end-to-end tests for source upload -> ready -> chat -> citation and artifact generation;
- security regression tests for cross-user access, external-provider policy, secret leakage, prompt-injection/tool-permission isolation, XSS/HTML sanitization, SSRF/provider-endpoint validation, cache isolation, derived-content restriction propagation and execution staging;
- execution-provider tests proving forbidden host paths/secrets/network paths remain inaccessible under the selected Bubblewrap policy, including no inherited connected sockets and malicious output symlink/path cases;
- job/API recovery tests covering worker retries/duplicate work, client command/idempotency-key retries, worker-lease expiry, orphan recovery and SSE/job-state reconnect after missed/expired events; if an external event bus is introduced, its duplicate-delivery/outbox behavior is tested too;
- source-refresh and parser/index-upgrade race tests proving in-flight chat/research/artifact jobs remain on their pinned `SourceVersion`/`CanonicalDocument`/retrieval-index generations while connector, parser or embedding generations advance;
- deletion/purge regression tests proving normal source removal excludes new retrieval without destroying retained historical evidence, while source privacy purge traverses AD-016 across caches/context snapshots, generated messages, source-derived/provenance-linked note revisions, artifact versions/renders, dependent study-session snapshots, run-evidence snapshots, research/tool/execution outputs, generated files and staged execution inputs that can retain the purged content, and chat-history deletion leaves no hidden content-bearing context snapshot of the deleted private conversation;
- composite-artifact tests proving parent versions pin exact child `ArtifactVersion`s and do not mutate when children are revised/deleted;
- parser/isolation regression tests proving risky/native parser/OCR/converter/media processes cannot access application/provider secrets, uncontrolled network, arbitrary host paths or exceed configured resource/time limits, and proving the default generated-code Bubblewrap profile has no network path;
- hostile-source/web prompt-injection tests proving source/page instructions cannot grant new tools, broaden authorization, select forbidden providers, access secrets, bypass egress restrictions or trigger side effects without the normal policy/tool gates;
- provider-credential ownership tests proving one user's personal API key cannot be consumed by another user, a shared notebook default or anonymous/share-link traffic;
- mid-job authorization-revocation tests proving membership/source revocation blocks subsequent external dispatch, execution staging and result publication;
- account-lifecycle tests proving disablement is immediate even for a sole owner, sole-owner notebooks enter locked custody, audited metadata-only custody can transfer/schedule deletion without granting content access, final deletion cannot leave an ownerless notebook, and private conversations, private agent/research traces/context snapshots and personal credentials are removed according to policy;
- blob crash-consistency tests that inject failure before/after temporary write, finalization and DB commit; reconciliation must collect safe orphans and flag missing/corrupt referenced blobs without silent data loss;
- derived-restriction tests proving restricted source material cannot be exposed through generated messages/notes/artifacts, notebook copies, share links or exports unless the connector/source policy explicitly permits that transformed use;
- trusted-reverse-proxy-auth tests proving spoofed client identity headers are ignored/overwritten and a deployment cannot enable that mode while leaving an unauthenticated direct backend path;
- migration/restore tests for supported upgrade paths and validation of the reference backup RPO/RTO envelope;
- parity-contract tests for the documented stable reference behaviors that are easy to regress: document-level citation fallback for very short sources, private chat histories in shared notebooks, notebook-copy exclusions, share-link revocation on resource deletion, slide length/revision/export controls and type-appropriate artifact downloads;
- study-context privacy tests proving explicit performance follow-up pins the requesting user's immutable `StudySessionSnapshot` + exact `ArtifactVersion`, cannot observe later progress mutations mid-request and never exposes another collaborator's answers/results.

Tests MUST NOT require paid external APIs to run the ordinary CI suite. Optional live-provider smoke tests may run separately.

## 3. Parser and provenance golden corpus

Maintain representative fixtures for PDF, DOCX, PPTX, spreadsheet, EPUB, HTML, images/OCR, audio/transcripts and malformed/adversarial samples. Expected canonical nodes and source locators are versioned so parser upgrades can reveal provenance regressions explicitly.

## 4. Authorization regression suite

Every resource class and indirect access path is tested across users/notebook memberships/roles, including retrieval filtering, artifact evidence, downloads, research agents, connector credentials and execution input staging. Connector/source-access revocation must also be tested against caches, historical citation resolution and new artifact generation. Cross-user/source leakage is a release blocker.


- Collaboration/privacy tests MUST prove one notebook member cannot enumerate/read another member's private chat history or raw Agentic Chat/research/tool traces merely because the notebook is shared.
- Administrator-boundary tests MUST prove installation-administrator status alone does not grant notebook-content access, that metadata-only custody actions do not imply content access/membership, and that any separate break-glass content mechanism is explicit and audited.
- Notebook-copy tests MUST prove chat history/notes are excluded from the parity copy operation and source access/restrictions are re-evaluated.
- Sharing tests MUST prove source-level access/reuse restrictions block every applicable read/copy/share-link/download/export/publication path and cannot be bypassed by summarizing, transforming, embedding or copying the source through a generated artifact.

## 5. Provider compatibility suite

Each adapter is tested against the internal capability contract: streaming, errors, tool calls, structured output, multimodal parts where applicable, cancellation, usage accounting and retry semantics. Unsupported capabilities must fail predictably rather than being silently emulated incorrectly.

## 6. Reproducible builds and dependencies

Language/package dependencies SHOULD be locked. Container/package artifacts SHOULD be reproducible enough to identify exact dependency versions. Releases SHOULD publish an SBOM or equivalent inventory and record versions of high-risk native components such as PDF/media parsers, browser engines and Bubblewrap.

## 7. Security update policy

Critical fixes affecting isolation, authentication/authorization, remote code execution, file parsing or secret handling require expedited release/backport handling. Deployment health checks SHOULD flag known-unsafe minimum versions where practical.

## 8. Release gates

A release candidate MUST require:

1. software test suite passing;
2. schema migration + rollback/restore validation for the supported upgrade path;
3. no unresolved release-blocking security findings;
4. core AI evaluation suite not regressing beyond defined tolerances;
5. source-to-citation end-to-end path passing;
6. a smoke test with at least one local provider configuration;
7. automated accessibility checks plus manual keyboard/focus smoke coverage for primary workflows against the WCAG 2.2 AA target;
8. the lightweight reference performance/job-visibility acceptance suite; and
9. a periodically exercised backup/restore test demonstrating the documented reference RPO/RTO envelope.

The performance and restore suites MUST publish the Chapter 21 reference-profile fixture/tool version, dataset counts, storage size, concurrency, warm-up method and measured percentiles/timestamps. A latency or RTO number without the corresponding profile is not a release-gate result.

## 9. Versioning

Application releases, DB schema, externally supported API versions (if any), artifact recipes, canonical-document schema, parser versions and model-provider adapters require explicit version identifiers. Compatibility promises can differ by interface, but breaking changes must be documented and migratable.


## 10. Mutable-note and generation-input regression tests

Tests MUST verify that any operation using note context pins an exact `NoteRevision`, that notebook/custom-instruction, output-language and conversation-history changes cannot affect an in-flight operation, that concurrent collaborator edits cannot change an in-flight operation, that notes do not leak into ordinary source-only chat unless the explicit note-context capability is invoked, and that note-kind editability rules are enforced (including non-editable saved-response notes where parity requires it). Chat turns MUST pin the exact prior-message context used for generation. Starting/resetting to a new conversation must not rewrite retained historical manifests, while explicit delete-history must purge the deleted private messages and content-bearing conversation-context snapshots/caches and may intentionally break their reproducibility. Note-to-source promotion must create a normal immutable source snapshot and preserve derivation metadata. Agent/research tests MUST prove that the initial run snapshot remains immutable while newly discovered tool results are appended as immutable provenance-bearing records, and that each later planning/synthesis/final model step records a child `GenerationInputManifest` containing exactly the evidence available to that step. Tests must also prove that private raw tool traces are not exposed through a shared artifact merely because the artifact retains a minimal `RunEvidenceSnapshot` citation dependency.

## 11. Technical-specification traceability contract

This architecture is not itself a list of implementation test functions. The technical specification derived from it MUST create and maintain a machine-readable requirements-and-tests ledger. Every architecture or technical-specification occurrence of `MUST`, `MUST NOT`, `SHOULD` or `SHOULD NOT` (case-insensitive under Chapter 00) is classified and receives a stable requirement identifier unless explicitly recorded as narrative/non-requirement text. Every classified normative requirement maps to one or more of:

- an automated test identifier;
- a manual test identifier where automation cannot provide the required evidence;
- a documented inspection/analysis identifier for a property that cannot be exercised directly; or
- an explicit, approved deferral with rationale and target milestone.

No release may contain an unclassified normative requirement. A `SHOULD`/`SHOULD NOT` that is not implemented requires a reviewed deviation with rationale, risk, compensating behavior where relevant and target/reconsideration point; it does not silently disappear because it is not an absolute `MUST`. The ledger records requirement source, subsystem owner, implementation component, test level, fixture, oracle, execution tier and most recent result/evidence. Generated coverage percentages do not replace this traceability rule. A test that executes code but does not assert the requirement's observable invariant does not count as coverage.

Each implementation work item MUST include acceptance criteria and the requirement/test identifiers it adds or changes. A behavior-changing implementation is not complete until its positive path, relevant denial/failure paths and required observability have tests. Defect fixes MUST include a regression test that fails before the fix where a deterministic reproduction is feasible.

### 11.1 Capability/conformance profile and `N/A` rules

Per AD-026, each phase acceptance build and release candidate publishes a machine-readable profile that records every Chapter 02 capability as stable/core, advanced/provider-dependent, late/optional, provisional/announced or deliberate non-target; whether it is implemented and enabled; required providers/runtime dependencies; and the activated automated/manual test ids.

`Not applicable` is permitted only for a declared disabled optional capability, a provisional feature not claimed by the release, or a deliberate non-target. It requires a reason in the result. A stable/core capability in the accepted milestone, an enabled code path, or a cross-cutting security/privacy/provenance/purge requirement cannot be marked `N/A`. Enabling an optional capability automatically activates its provider contract, authorization, disclosure, data-lifecycle, security, failure/recovery and manual/perceptual tests. A feature hidden only because a dependency is temporarily down remains implemented and must retain test coverage.

## 12. Required test-case form and oracle hierarchy

Every canonical automated or manual test MUST state:

1. stable test id and mapped requirement ids;
2. purpose and risk addressed;
3. preconditions, actors/roles and fixture versions;
4. exact inputs/actions, including concurrency or failure injection where relevant;
5. observable expected results and forbidden side effects;
6. authoritative oracle and allowed tolerance;
7. cleanup/isolation requirements; and
8. evidence retained on failure and, for release/manual tests, on success.

Use the strongest available oracle in this order: exact domain invariant; schema/contract validation; versioned golden output; deterministic fake-provider result; bounded property/statistical assertion; rubric-based human evaluation. Snapshot/golden tests require semantic assertions for critical fields so a broad snapshot update cannot silently approve a regression. Real-model wording MUST NOT be asserted as exact text unless the model and decoding path are deterministic; tests instead assert evidence selection, citation validity, schema, policy, state transitions and bounded quality metrics.

Security, authorization, privacy, purge, durability, provenance and migration invariants require a 100% pass rate. Retries cannot convert their failure into a pass. AI-quality thresholds are versioned with the evaluation corpus and must be fixed before a release candidate is evaluated; changing a threshold or corpus requires a reviewed result comparison rather than silently resetting the baseline.

## 13. Deterministic reference test harness

The technical specification MUST select and lock concrete test tools, but its harness must provide these capabilities independent of language/framework choice:

- disposable PostgreSQL and blob-store instances using production schemas and migrations for integration/E2E tests; in-memory substitutes are limited to unit tests where persistence semantics are irrelevant;
- deterministic factories for users, roles, notebooks, memberships, source versions, notes, conversations, artifacts, jobs and provider policies;
- controllable clock, random/identifier source and scheduler/failure-injection seams where timing, leases, retries or races are under test;
- a fake model/provider server supporting streaming, cancellation, structured output, tool calls, usage records, delayed/malformed/error responses and deterministic embeddings;
- fake synchronous and remote-asynchronous image/video/speech providers supporting operation ids, idempotency keys, polling, signed/unsigned callback verification cases, duplicate/out-of-order/late callbacks, refusal, cancellation races, expiry, malformed assets and uncertain submission outcomes;
- fake connector/search/fetch services supporting revisions, revocation, deletion, rate limits, hostile content and SSRF targets without reaching the public internet;
- versioned source fixtures for every supported Chapter 02 source family and acquisition behavior, including plain/pasted text, Markdown, PDF, DOCX, PPTX, CSV/spreadsheets, EPUB, HTML/web snapshots, images/OCR, audio/transcripts, transcript-backed public video, connector refresh/revocation, tiny sources, multilingual content, malformed files, active-content attempts and large-but-bounded inputs;
- versioned generated-media fixtures covering browser-supported and unsupported codecs/containers, multiple tracks, captions, thumbnails, truncation/polyglots, corrupt headers, excessive dimensions/duration and otherwise valid provider output;
- an isolated execution fixture that runs the production Bubblewrap policy and can prove denied filesystem, secret, device, process and network access;
- a real-browser E2E driver such as Playwright or an equivalent selected by the technical specification, with retained screenshots/traces/console/network logs on failure; and
- seed commands that create the same reference notebook and actors for automated and manual testing.

Ordinary CI MUST be hermetic: no paid API, uncontrolled public-web dependency or developer account is required. Optional live-provider/connector smoke tests use dedicated least-privilege test credentials, are clearly separated from deterministic gates, redact secrets/content and cannot be the only coverage of a contract.

## 14. Canonical automated end-to-end journeys

The technical specification may split these journeys into smaller tests, but it MUST preserve their end-to-end assertions and identifiers in the traceability ledger:

| ID | Journey | Mandatory assertions |
|---|---|---|
| E2E-001 | Local account -> notebook -> upload -> ready -> ordinary chat | Durable asynchronous ingestion, selected source version, grounded answer, resolvable citation navigation, no tool/web use and retained private history. |
| E2E-002 | Heterogeneous/multi-source notebook | Source include/exclude behavior, lexical/vector evidence fusion, table/image/text locator handling, tiny-source document-level fallback and no evidence from an unselected source. |
| E2E-003 | Studio generation | Prompt/customization capture, queued/background completion, unread notification state, immutable artifact version, correct viewer and type-appropriate export/download. |
| E2E-004 | Notes workflow | Concurrent editing/lost-update protection, exact note revision pinning, supported transformations, saved-response editability rule, note-to-source derivation and absence from ordinary source-only chat unless selected. |
| E2E-005 | Collaboration, sharing and copy | Owner/editor/viewer permissions, user-private chat, dependency-derived restrictions, public/artifact-link policy, revocation/deletion invalidation and notebook copy containing permitted sources/artifacts but excluding notes/chat. |
| E2E-006 | Refresh/version race | Old generation remains pinned while a new source/parser/index generation activates atomically; failed refresh never replaces known-good active state. |
| E2E-007 | Study flows | Persistent per-user progress, collaborator isolation, exact artifact/session snapshot for performance follow-up and no mutable or cross-user state leakage. |
| E2E-008 | Agentic research/code | Explicit agentic mode, budget/tool authorization, provenance-bearing web/tool evidence, Bubblewrap isolation, validated outputs and no private raw-trace leakage through shared artifacts. |
| E2E-009 | Failure/reconnect/cancellation | Idempotent command retry, browser disconnect/reconnect, missed-event resynchronization, cancellation, worker death/lease recovery and no duplicate committed output. |
| E2E-010 | Removal, purge and account lifecycle | Immediate exclusion, complete AD-016 purge closure, disabled-user denial, sole-owner custody and no ownerless or secretly retained private content. |
| E2E-011 | Provider policy and disclosure | Local preference, visible disclosure before/while content-bearing external use, policy-denied fallback, credential ownership and auditable route selection. |
| E2E-012 | Upgrade and recovery | Supported migration, rollback/restore procedure, DB/blob integrity, degraded index rebuild visibility and Chapter 21 RPO/RTO evidence. |
| E2E-013 | Multimodal/video lifecycle | Capability negotiation, source-grounded storyboard/script, synchronous and remote-asynchronous provider paths, callback/poll reconciliation, no duplicate billable submission, validated original + derived rendition provenance, seekable authorized playback, refusal/fallback, cancellation and purge of every derivative. |

All primary web journeys MUST run through the public browser/API boundary rather than invoking internal services directly. Lower-level integration tests may prepare expensive fixtures, but the behavior under test must still cross its real boundary. At least one release-gating path uses production-equivalent packaging and service supervision on GNU/Linux.

## 15. Manual end-to-end and exploratory runbook

Manual testing is reserved for properties that require perceptual, hardware/browser or human-judgment evidence; it is not a substitute for automatable assertions. The repository MUST contain a versioned runbook using the test-case form in Section 12. Each run records release/build, environment, browser/OS, tester, timestamp, result, deviations and evidence links. Failed steps create a tracked defect; a vague “looks good” sign-off is invalid.

The release-candidate runbook MUST cover:

| ID | Manual scenario | Required evidence/pass condition |
|---|---|---|
| MAN-001 | First-use source-to-citation workflow | A new user can complete the workflow without hidden setup; citation opens the correct human-visible source context and errors are actionable. |
| MAN-002 | Audio Overview | Generate, play/pause/seek, change speed where supported, download, resume/background behavior and interactive interruption where implemented; intelligibility and controls are human-verified. |
| MAN-003 | Video, slides, infographic and report rendering | No clipping/corruption, usable navigation/zoom, readable citations, correct download formats and acceptable representative desktop/responsive layouts. |
| MAN-004 | Keyboard, focus and screen-reader smoke | Primary workflows have logical focus order, visible focus, operable controls, announced status/errors and no keyboard trap against the WCAG 2.2 AA target. |
| MAN-005 | Responsive web workflow | Source, chat, Studio, job status and artifact viewing remain usable at the supported narrow viewport; native-app-only/share-sheet/offline behavior is not claimed. |
| MAN-006 | External-provider disclosure and policy | A human can identify that content will/is being sent externally, which provider is used and why an action is blocked under local-only policy. |
| MAN-007 | Long-running work and recovery | Close/reopen the browser, reconnect after network loss, inspect progress/failure, retry/cancel safely and find the completed durable artifact. |
| MAN-008 | Backup/restore operator drill | A person following only the maintained operations documentation restores the reference fixture and obtains the required integrity/health evidence within the measured envelope. |
| MAN-009 | Realtime voice/recording (conditional) | When either provisional capability is enabled: verify permission denial, device selection/loss, interruption, transcript/privacy indicators, latency and recovery. |
| MAN-010 | Source-grounded video quality | For each enabled baseline video path, verify narration/evidence faithfulness, visual factual consistency, source attribution, caption timing, A/V synchronization, seek/full-screen/download behavior and intelligible failure/refusal messaging on representative desktop and narrow layouts. |

All `N/A` results follow Section 11.1: an enabled media/video path cannot skip its applicable manual scenario merely because it uses an optional provider.

Exploratory charters SHOULD cover hostile/unexpected source combinations, long multilingual notebooks, concurrent collaborators, accessibility edge cases and interrupted media/tool workflows. Findings feed deterministic regressions whenever reproducible.

## 16. Browser, CI and execution tiers

The technical specification MUST publish a supported browser matrix. Automated primary-workflow E2E tests run against at least Chromium and Firefox on GNU/Linux; release manual checks use those browsers at minimum. Additional engines may be supported only when they are included in the declared matrix and test evidence.

The default execution tiers are:

- **pre-commit/local:** fast unit, schema/static and focused component tests;
- **pull request:** all unit tests, deterministic integration/contract tests, migration-from-current tests, security-policy regressions and a browser critical-path subset;
- **nightly:** complete browser E2E, parser corpus, property/fuzz/race suites, hostile-input/security tests, backup/restore on a reduced fixture and optional isolated live-provider smoke tests;
- **release candidate:** all release gates, full supported-upgrade matrix, Chapter 21 performance/recovery profile, supply-chain scans and the manual runbook; and
- **periodic security/operations:** longer fuzzing, dependency/container scanning, secret scanning, restore drills and sandbox escape-policy verification after relevant kernel/Bubblewrap/runtime changes.

CI publishes JUnit-equivalent machine results plus logs and relevant browser traces/screenshots, sanitizer/fuzzer artifacts, benchmark profiles and restore evidence. Secret-bearing or private source content is redacted before retention.

## 17. Meaningfulness, nondeterminism and flaky-test policy

Line/branch coverage is diagnostic, not the release definition. The technical specification MUST set coverage expectations per subsystem and use risk-focused review, property tests, mutation testing or equivalent fault-seeding on critical pure domain/policy code to demonstrate that assertions detect plausible defects. Unreviewed mass snapshot regeneration is forbidden.

Deterministic tests do not automatically retry to obtain a passing status. Suspected infrastructure failure may be rerun for diagnosis, but both attempts remain visible. A flaky test receives an owner, issue, quarantine reason and expiry; quarantined tests remain reported, and tests protecting security, authorization, privacy, purge, migration, durability or core source-to-citation behavior cannot be waived from a release gate merely for being flaky.

Real-model evaluation runs record model/version, decoding configuration, corpus version and repetition count. Statistical comparisons report sample counts and uncertainty; a single favorable rerun cannot erase a regression. Human/rubric evaluation uses blinded or randomized comparison where practical and stores adjudication rules.

## 18. Definition of done for technical-specification handoff

Before implementation begins for a subsystem, its technical specification MUST define interfaces/schemas, persistence and migration behavior, security/policy boundaries, observability, failure/idempotency semantics, fixtures and mapped automated/manual acceptance tests. Before a feature is called complete:

- its traceability entries have no unexplained gaps;
- its capability/conformance profile is current and activates the correct test set;
- required deterministic tests pass at their assigned tier;
- relevant canonical journeys pass through real public boundaries;
- manual/perceptual steps have current evidence where applicable;
- failure, denial, cancellation and recovery paths are covered;
- documentation/operations/migration impacts are updated; and
- no new external dependency, permission or provider assumption bypasses the decisions in Chapters 00–24.

This contract gives an implementation agent enough structure to generate concrete tests while preventing it from inventing product semantics or approving itself through weak assertions. The technical specification may choose frameworks and split cases differently, but it may not weaken the mapped invariants or omit the evidence required by this chapter.
