# 21 — Non-Functional Requirements

## 0. Reference acceptance profile

Terms such as “reference profile” and “published storage envelope” are measurable only with a fixed baseline. Unless a release publishes a replacement profile, acceptance testing uses:

- one GNU/Linux x86-64/ARM64 host with **8 CPU cores, 16 GiB RAM and SSD/NVMe storage sustaining at least 500 MB/s sequential read/write**;
- local PostgreSQL plus local-filesystem blob storage, one web/API process and at least two ordinary background-worker slots; model inference may run elsewhere and model/search-provider time is excluded where a requirement says so;
- a seeded database of **25 users, 250 notebooks, 5,000 retained source versions, 2 million retrieval chunks and 20,000 artifact/message/note records**;
- a primary-data envelope of at most **50 GiB PostgreSQL data and 200 GiB blob data** for the reference backup/restore test;
- the non-model API latency workload runs for at least ten minutes after a documented warm-up with **10 concurrent authenticated clients** and a representative 90% read / 10% write mix over notebook lists/details, memberships, source/artifact metadata, job state and preference updates; uploads/download payload transfer, parsing, models and media rendering are excluded;
- job-visibility latency is measured from committed job-state transition to presentation in a continuously connected client over at least 1,000 transitions, including stream reconnect/resynchronization cases as a separate test.

These values are a reproducible acceptance baseline, not minimum production hardware or a capacity promise. Releases MUST publish the exact benchmark fixture/tool version and any deliberate profile change with the result.

## 1. Reliability

- Canonical source data and user-authored content must survive worker/model failures.
- Derived indexes must be rebuildable.
- Long jobs must be restartable/retryable where practical.
- A failed provider should not corrupt notebook state.
- Orphaned durable jobs MUST be detected and recovered/failed within the configured lease-expiry interval plus one scheduler/reaper cycle; no accepted durable job may disappear silently after worker restart.

### 1.1 Data integrity and concurrency

Mutable resources SHOULD use transactions plus optimistic versioning/ETags or equivalent lost-update protection where concurrent edits matter. Derived-state rebuilds must never replace a known-good active index with a partial/failed build; activation of a successfully rebuilt derived state must be atomic from readers' perspective. Persisted blobs MUST carry expected size plus a cryptographic content checksum (or a content-addressed key providing the equivalent invariant), and the AD-024 reconciliation process must detect orphan and missing/corrupt referenced objects.

## 2. Performance

The following are **reference acceptance targets**, not hosted-service SLAs; installations may publish stricter/looser targets for their hardware. Measurements exclude external model/search-provider latency unless stated otherwise.

- Ordinary authenticated metadata/resource reads and writes that do not invoke models or heavy parsing SHOULD meet **p95 <= 500 ms** on the documented single-host reference test profile.
- Persisted job-state changes SHOULD become visible to a connected browser through polling/streaming within **2 seconds p95**, excluding a disconnected client's reconnect delay.
- Chat/generation paths MUST stream incremental output when the selected provider supports streaming; application code must not buffer a complete provider response before exposing it.
- Ingestion SHOULD expose incremental readiness/progress and use parallel parsing/embedding only where ordering, resource and provenance constraints remain safe.
- Embedding SHOULD support batching, and model/provider prefix caching MAY be used when it does not violate authorization/privacy boundaries.
- Heavy artifact/media/research work is asynchronous and MUST NOT depend on one long-lived browser request.

## 3. Scalability

The baseline target is a small trusted team, but no core data model should assume exactly one user or one model server. Worker pools and model endpoints should be horizontally separable later.

## 4. Portability

Server runtime targets GNU/Linux. AI providers, databases and object stores remain replaceable. The frontend should require only a modern browser.

## 5. Maintainability

Subsystem boundaries must have explicit interfaces. Domain services should not import provider SDKs directly. Parser/model/index versions are recorded so migrations are explainable.

## 6. Reproducibility

Generated content should retain enough metadata to understand how it was produced: a coherent immutable per-generation input manifest of exact source/canonical representations, explicitly selected note revisions, artifact/run-evidence dependencies, an explicit user-private study-session snapshot where used, resolved notebook/user/request instruction snapshot, exact prior conversation-message context (for chat), retrieval/index/prompt/recipe version, provider/model identifier, relevant settings and evidence references. No completed generation step may silently combine source refreshes, note edits, study-progress changes, conversation-context changes or artifact revisions introduced after that step's manifest was resolved. Agentic/research runs may intentionally add newly acquired immutable tool evidence between steps, which is recorded in child manifests and the append-only run trace.

Exact bit-for-bit reproducibility is not guaranteed for nondeterministic external models.

## 7. Accessibility

Primary end-user web workflows (notebook/source navigation, chat, Studio, settings and sharing) SHOULD conform to **WCAG 2.2 AA**. They must be keyboard-operable, expose meaningful focus/state/labels to assistive technology and avoid relying on color alone for required meaning. Generated audio/video SHOULD support transcripts/captions where the underlying pipeline can produce them; inaccessible generated-media formats should have a text alternative where practical.

### 7.1 Data portability

Baseline portability is provided by documented backup/restore plus ordinary source/artifact exports. A bespoke cross-installation whole-notebook interchange bundle is useful but beyond parity and therefore deferred until there is a concrete migration need.

## 8. Internationalization

The data model must support Unicode and multiple source/output languages. A user-level output-language preference SHOULD act as the default for generated text/media, with per-request/artifact override when supported. UI localization can be incremental and is independent of output language. Language-specific tokenization/search behavior should be pluggable.

## 9. Backup/restore

A documented backup strategy must cover transactional DB, object storage and configuration/secrets, including a separate recovery procedure for the installation secret/master key used to protect stored credentials. Backups must be coordinated sufficiently to restore a mutually consistent database/object snapshot. Derived indexes may be excluded if rebuildable, but doing so affects recovery time.

For the documented single-host reference deployment, the baseline disaster-recovery target is **RPO <= 24 hours** and **RTO <= 4 hours** within Section 0's 50 GiB database + 200 GiB blob envelope. The backup schedule must therefore leave no successful recoverable point older than 24 hours under normal operation; monitoring must alert when that bound is missed. RTO is measured from declaring the restore exercise started to the application passing integrity checks and serving authenticated metadata/source reads, with rebuildable indexes allowed to continue rebuilding only if their degraded state is explicit. These are minimum reference targets rather than a prohibition on WAL archiving, snapshots or tighter site-specific goals. Restore procedures MUST be exercised in release/operations testing; a backup that has never been restored is not considered validated.

## 10. Upgradeability

Schema migrations, provider/adapter compatibility and artifact/source parser versions require explicit migration/version strategies. Parser/canonical/index upgrades activate new immutable derived generations rather than rewriting representations referenced by retained outputs. Upgrades must not silently orphan old artifacts or citations.

## 11. Testability

Every bounded context MUST be testable without requiring a live commercial model provider. Provider adapters need deterministic mocks/recorded fixtures, including remote-asynchronous media operations; parsers and provenance resolvers need golden fixtures; API/authorization rules need integration tests; the critical source-to-citation and source-to-artifact paths need end-to-end coverage. AI quality evaluation (Chapter 18) complements rather than replaces ordinary software testing. The technical specification and implementation MUST follow Chapter 25's requirements-to-tests traceability ledger, AD-026 capability/conformance profile, deterministic harness, canonical automated journeys, manual runbook and release evidence rules; unclassified normative requirements are not implementation-ready.

## 12. Dependency and supply-chain hygiene

Runtime dependencies SHOULD be pinned/locked reproducibly, continuously scanned for known vulnerabilities, and updated on a defined cadence. Releases SHOULD be able to emit an SBOM or equivalent dependency inventory. Native parsers, media tools, browser components and Bubblewrap deserve expedited security update handling because they process untrusted input or form isolation boundaries.

## 13. Operability and degraded mode

Every deployable service SHOULD expose lightweight liveness and dependency-aware readiness/health status. Startup/readiness checks SHOULD detect incompatible database schema versions, inaccessible object storage, unavailable queues and unsupported Bubblewrap/user-namespace prerequisites. Provider/model endpoints are dynamic dependencies: one unavailable model provider SHOULD degrade only the capabilities/routes that require it rather than make the notebook application unavailable when a viable fallback or unrelated capability remains. Administrator diagnostics SHOULD surface degraded dependencies without leaking secrets.
