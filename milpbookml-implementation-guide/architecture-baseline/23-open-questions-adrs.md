# 23 — Architecture Decisions and Implementation Choices

This chapter is the handoff ledger for decisions. **No architecture-blocking open questions remain in v0.10.** Items that are intentionally not frozen are implementation selections that can be changed without altering the domain model or subsystem boundaries.

## 1. Resolved questions from the planning review

### Q-001 — External-provider default policy and disclosure

**Resolved as AD-011.** Suitable local providers are preferred when configured. External providers remain allowed unless installation/notebook policy disables them. Any content-bearing call to an external provider/service is visibly disclosed to the initiating user, including fallback.

### Q-002 — Network access inside Bubblewrap executions

**Resolved as AD-012.** The default execution profile has no direct network access. Controlled web/research tools acquire external data and stage it into the isolated workspace. Any future network-enabled execution profile is an explicit administrator policy choice.

### Q-003 — Remote-source refresh semantics

**Resolved as AD-015.** Uploaded/local files are immutable snapshots. Ordinary web URL imports refresh manually by default. A connector may auto-refresh only with reliable upstream revision/change signals and access-revocation semantics. New revisions become retrieval-active atomically only after required processing succeeds; users can pause/pin refreshable sources where meaningful; in-flight operations remain pinned to their original versions.

### Q-004 — Authentication integration

**Resolved as AD-018.** Local accounts are the baseline. Generic OIDC/trusted reverse-proxy authentication is optional for installations that already have identity infrastructure. No external identity provider is required.

### Q-005 — Initial persistence/orchestration stack

**Resolved as AD-017.** The minimal reference deployment uses PostgreSQL for transactional data plus PostgreSQL FTS/`pgvector`, PostgreSQL-backed durable jobs/leases/outbox, and a blob abstraction backed by the local filesystem by default. Dedicated search/vector/broker/object-store services are scale-out substitutions, not baseline dependencies.

### Q-006 — Initial embedding and reranker models

**Reclassified as an implementation benchmark, not an architecture decision.** The model-provider/retrieval contracts already permit replacement. Defaults should be selected using the evaluation corpus for multilingual quality, retrieval quality, hardware cost and latency.

### Q-007 — Web research backend

**Reclassified as a provider/tool implementation choice.** The architecture requires a provider-neutral search/fetch/browser tool contract, provenance, SSRF controls, cancellation and budgets. The concrete search provider(s) or self-hosted search engine can be selected later without changing the agent domain.

### Q-008 — Provider configuration UX

**Resolved as AD-019.** Administrators own installation providers/trust/defaults; users may add personal providers only when policy permits; notebook overrides select only from allowed capabilities. Per-request overrides are optional UX.

### Q-009 — Frontend/backend implementation stack

**Reclassified as an implementation selection.** Framework choice must satisfy the API, streaming, job, typing/schema, security and deployment contracts in this specification, but is not part of notebook architecture.

### Q-010 — Source/notebook limits

**Reclassified as installation policy.** Limits are configurable based on hardware and benchmark results rather than copied from the reference product.

### Q-011 — Hard deletion versus historical reproducibility

**Resolved as AD-016.** Removing a source excludes it from future retrieval immediately while referenced historical versions may remain under retention policy. Explicit hard/privacy purge deletes primary content and traverses the complete known content-bearing dependency closure (including derived note revisions, artifacts/renders, run evidence, research/tool/execution outputs, generated files, request/context snapshots and caches), intentionally breaking affected historical dereferencing. Notebook deletion follows a documented grace/trash policy before purge. Backups expire deleted content according to finite backup retention. Privacy/purge wins over reproducibility.

## 2. Resolved ADR index

- **AD-001** Self-hostable multi-user deployment.
- **AD-002** GNU/Linux server target.
- **AD-003** Provider-neutral internal model API.
- **AD-004** Big Pickle is a replaceable external/bootstrap candidate, never a dependency.
- **AD-005** Local models are first-class.
- **AD-006** Provenance-first canonical source architecture.
- **AD-007** Generic Studio artifact framework.
- **AD-008** Agent runtime separated from ordinary grounded chat.
- **AD-009** Bubblewrap-based isolated local execution provider.
- **AD-010** Evaluation/observability are core.
- **AD-011** Local-first routing; external providers allowed by default with mandatory disclosure.
- **AD-012** No direct network in the default execution profile.
- **AD-013** Product/identity independence; no Google-account/vendor-ecosystem coupling.
- **AD-014** No multi-workspace/organization layer in the baseline.
- **AD-015** Snapshot/manual-refresh default; connector auto-refresh only with safe version semantics.
- **AD-016** Explicit remove vs hard-purge lifecycle; privacy deletion overrides reproducibility.
- **AD-017** Minimal PostgreSQL-centric reference persistence/job stack.
- **AD-018** Local-account authentication baseline; optional generic SSO integrations.
- **AD-019** Installation/user/notebook provider-configuration scopes.
- **AD-020** User-scoped provider credentials cannot be consumed by other users/shared notebook defaults.
- **AD-021** Long-running work revalidates authorization at security-sensitive boundaries and before publication.
- **AD-022** Immediate account disablement plus audited metadata-only custody prevents ownerless notebooks without granting administrators content access; deletion resolves ownership and removes user-private state/credentials.
- **AD-023** Derived content retains effective dependency-derived access/reuse restrictions; generation is not permission laundering.
- **AD-024** Database/blob persistence uses an explicit crash-consistent finalize/reference/reconciliation lifecycle.
- **AD-025** Technical-specification handoff requires normative traceability, meaningful automated/public-boundary tests and repeatable manual evidence where automation is insufficient.
- **AD-026** Each milestone/release publishes a capability/conformance profile that determines test applicability without allowing stable/core or enabled security/lifecycle behavior to disappear behind `N/A`.

## 3. Implementation selections intentionally deferred

These are **not missing architecture**. They should be decided with prototypes/benchmarks during implementation:

- backend language/framework;
- frontend framework;
- default embedding model;
- default reranker;
- concrete web-search provider(s);
- headless-browser engine;
- exact parser libraries for each format;
- local-filesystem versus S3-compatible blob backend for a particular installation;
- systemd/package versus Compose-style packaging;
- installation-specific concurrency/storage/source limits.

Any chosen implementation must satisfy the normative contracts in Chapters 00–25. A choice that requires changing the notebook/domain model or bypassing the provider/provenance/policy abstractions is an architecture change and requires a new ADR.
