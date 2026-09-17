# 00 — Status, Decisions and Normative Language

## 1. Purpose

This chapter records what is already decided, what remains deliberately abstract, and how requirements in the rest of the specification should be interpreted. It is intended to prevent architectural decisions from becoming implicit assumptions scattered through implementation code.

## 2. Normative terms

The words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are used in their ordinary requirements-engineering sense:

- **MUST / MUST NOT**: required for architectural conformance.
- **SHOULD / SHOULD NOT**: strongly preferred; deviation requires a documented reason.
- **MAY**: optional or implementation-dependent.

Within the numbered architecture chapters, these terms are normative when used to express an obligation, recommendation or permitted option **regardless of capitalization**; uppercase is the preferred editorial form. The technical-specification requirements extractor MUST scan them case-insensitively and either assign a stable requirement id or explicitly classify a narrative/non-requirement occurrence. `README.md`, `CHANGELOG.md` and the validation record are explanatory/non-normative unless they quote or link to a numbered requirement. This rule prevents a lowercase “must” or “should” from escaping the Chapter 25 traceability ledger.

## 3. Resolved architecture decisions

### AD-001 — Deployment model

The system is a **self-hostable multi-user server application**. A single installation may serve one person or a trusted team. It is not designed as a public multi-tenant SaaS, and the baseline architecture does not include billing, Internet-scale tenancy, or hosted-service infrastructure. Proper user, notebook ownership/membership and permission concepts are required because the installation itself is multi-user. A separate multi-workspace/organization tenancy layer is not part of the baseline.

### AD-002 — Operating-system target

The primary supported deployment target is **GNU/Linux**. Linux-specific primitives are allowed for the execution provider and service isolation. Portability to Windows/macOS is not a baseline requirement for the server.

### AD-003 — Provider neutrality

Model providers are replaceable. Application services MUST target internal capability interfaces rather than vendor SDKs. Provider identifiers may be stored as generation metadata, but never as structural dependencies of notebook objects.

### AD-004 — Initial LLM candidate

OpenCode / **Big Pickle** is the initial **external/bootstrap LLM candidate** because OpenCode currently lists it as a free, limited-time stealth model. It MUST be configurable, benchmarked on notebook workloads and replaceable, and is not the overall routing preference when a suitable local provider is configured. OpenCode currently documents Big Pickle through an OpenAI-compatible chat-completions endpoint. Endpoint and authentication remain ordinary provider configuration rather than permanent assumptions. The system MUST make provider privacy policy visible because OpenCode states that data collected during Big Pickle's free period may be used to improve the model.

### AD-005 — Local models

Local models are a first-class deployment mode. The model gateway MUST support adapters for local OpenAI-compatible endpoints and MUST permit native adapters where OpenAI compatibility would lose useful capabilities.

### AD-006 — Provenance-first knowledge architecture

Every extracted or generated knowledge element SHOULD be traceable to its originating source location. Citation provenance MUST survive parsing, chunking, retrieval and artifact generation.

### AD-007 — Generic artifact system

Reports, quizzes, slides, infographics, audio, video and future output types are specializations of a generic artifact lifecycle rather than separate ad-hoc applications.

### AD-008 — Agent separation

Agentic research and tool use are distinct from the ordinary notebook-grounded chat path. **Ordinary notebook chat MUST NOT silently invoke web/code tools**. Its normal factual grounding set is the selected notebook sources; when the user explicitly selects notes as prompt context, exact selected `NoteRevision`s may also be included. An explicit Agentic Chat mode MAY invoke tools, but the execution model, state tracking and permissions of long-running agents are managed separately.

### AD-009 — Code execution

Model-driven code execution is supported. Initial implementation uses a local GNU/Linux isolation layer built around **Bubblewrap**, a dedicated unprivileged execution identity, namespaces, an isolated root filesystem, resource limits and no-new-privileges. Bubblewrap is an implementation of `ExecutionProvider`, not part of higher-level domain contracts.

### AD-010 — Evaluation and observability

Evaluation, tracing, provider/model metadata and performance accounting are core services from the beginning. Retrieval changes and model changes should be benchmarkable rather than judged only by anecdotal use.

### AD-011 — External-provider default policy and disclosure

The installation is **local-first but not local-only**. Default role routing SHOULD prefer suitable local providers when configured. External providers remain allowed for every notebook and capability unless an installation/notebook policy explicitly disables them. Whenever an operation transmits user or notebook content to an external provider/service API, the UI MUST visibly notify the initiating user which external provider/model or capability is being used. Repeated calls that are part of one user-initiated operation MAY be grouped into one persistent operation-level disclosure rather than producing a notification per HTTP request. Provider choice and external/local status MUST also be retained in generation/job metadata.


### AD-012 — Execution networking

Model-generated code running through `ExecutionProvider` has **no direct network access by default**. The initial Bubblewrap profile MUST use a private/unshared network namespace and MUST NOT inherit connected sockets or other network-capable file descriptors. Web/research acquisition is performed through controlled agent tools and explicitly staged into the execution workspace. Administrators MAY later enable restricted egress profiles (for example an allowlisted proxy) or unrestricted egress, but these are non-default policy choices and must be visibly indicated for affected executions.


### AD-013 — Product and identity independence

The project is **not affiliated with Google and MUST NOT depend on Google identity, Google accounts, Google billing, Google product APIs or Google-specific backend services**. Gemini Notebook/NotebookLM is used only as an external behavioral reference for parity research. Optional connectors or model providers from Google may be implemented later through the same generic adapter boundaries as any other vendor, but none is required for login, storage, source ingestion, model routing, sharing or ordinary operation.

### AD-014 — Single-installation user/notebook scope

The baseline domain model is **installation -> users -> notebooks**. Notebook membership carries owner/editor/viewer permissions. A first-class organization/workspace hierarchy is intentionally deferred because the target is one self-hosted installation for a trusted team, not internal multi-tenancy. Installation-wide policy plus notebook policy and user preferences are sufficient for the baseline.
### AD-015 — Remote-source refresh semantics

Uploaded/local files are immutable snapshots. Ordinary web-URL imports are snapshots and refresh only on explicit user action by default. A connector MAY auto-refresh only when it exposes a reliable upstream revision/change signal and access-revocation semantics. Refresh produces a new immutable `SourceVersion`; the retrieval-active pointer changes only after required canonicalization/indexing succeeds. Users MUST be able to pause/pin a refreshable source where the connector supports refresh. In-flight operations remain bound to their pinned input manifests.

### AD-016 — Removal, deletion and purge

Removing a source from the active notebook corpus immediately excludes it from future retrieval/generation. Historical source versions MAY remain only while retained outputs reference them and policy allows that retention. A distinct **hard/privacy purge** irreversibly removes the source body from primary storage/indexes and MUST traverse the system's known ownership, provenance, dependency, cache and stored-request/context graph.

The purge traversal covers every **content-bearing system-controlled derivative** that can still retain material from the purged source, including canonical representations and derived indexes, generated `Message` bodies, source-derived or provenance-linked `NoteRevision`s, `ArtifactVersion`s and renders, dependent `StudySessionSnapshot`s, `RunEvidenceSnapshot`s, retained research/tool/execution outputs and generated files, prompt/conversation/context snapshots, staged execution inputs, and content-bearing caches. A dependent object may be deleted, invalidated, or replaced only through an explicit privacy-safe policy that guarantees the purged material is no longer retrievable; immutable historical objects are never silently rewritten to different content. Affected references resolve to a clear deleted/purged state rather than stale content.

The UI SHOULD preview the dependent object classes/counts that will be invalidated before destructive purge. Notebook deletion uses the installation's documented trash/grace policy, after which notebook-owned primary data is purged. Backups expire deleted content according to the documented finite backup-retention schedule rather than being surgically rewritten. Privacy/hard-purge policy takes precedence over reproducibility. The guarantee covers system-controlled copies that remain discoverable through the system's known relationships; it cannot recall data already transmitted to an external service or reliably discover independent manual copies/pastes whose provenance has been severed.

### AD-017 — Minimal reference persistence/orchestration stack

The reference self-hosted deployment SHOULD minimize mandatory services: PostgreSQL is the transactional store and initial lexical/vector store (PostgreSQL full-text search + `pgvector`), and durable jobs/leases plus transactional-outbox records MAY live in PostgreSQL initially. Original/large binary content is accessed through an object/blob abstraction whose default implementation may be the local filesystem; S3-compatible storage is an optional replacement. PostgreSQL's built-in full-text ranking is **not described as BM25**; BM25 or another lexical ranking implementation MAY replace or augment it behind the retrieval interface if evaluation shows a material quality benefit. Search/vector/job components remain behind interfaces so they can be split out if scale or performance later justifies it. Redis, a standalone message broker, Elasticsearch/OpenSearch, a dedicated vector database and MinIO are therefore **not baseline dependencies**.

### AD-018 — Authentication baseline

Local application accounts are the required baseline. Password-based local accounts use Argon2id (or a documented equivalently strong adaptive password hash) and secure server-side/session-cookie practices. Generic OIDC or trusted reverse-proxy authentication MAY be added for installations that already have identity infrastructure, but no external identity provider is required. If reverse-proxy authentication is enabled, identity headers are trusted only from explicitly configured proxy peers/boundaries; client-supplied copies are stripped or ignored, and the application backend MUST NOT be reachable through an unauthenticated path that bypasses that boundary.

### AD-019 — Provider configuration scopes

Installation administrators register installation-wide providers, credentials, trust classifications, role defaults and policy. Users MAY register personal provider credentials/endpoints only when installation policy allows it. Notebook-level model-role defaults MAY reference installation-scoped/shared providers permitted by policy, but MUST NOT make another user's personal credential a shared notebook dependency. A user MAY select their own permitted personal provider for operations they initiate. A per-request model override is optional UX and MUST remain constrained by the same policy/capability rules.

### AD-020 — Personal provider credential isolation

A user-scoped provider credential belongs to that user. It MUST NOT be used for an operation initiated by another user, background work attributed to another user, or an anonymous/public viewer merely because both users share a notebook. Shared notebook defaults therefore resolve only to installation-scoped/shared provider configurations. A user's personal provider can override routing only for that user's own permitted operations.

### AD-021 — Authorization revalidation for asynchronous work

Authorization is checked when an operation/job is accepted **and revalidated at security-sensitive boundaries while it runs**. Before a new external content dispatch, restricted-source read, execution-input staging, side-effecting tool call, or final result publication, the worker MUST confirm that the initiating actor still has the required notebook/source/capability permission. Revocation cannot recall data already transmitted to an external service, but it MUST prevent subsequent dispatch/publication and SHOULD cancel affected queued/running work where practical.

### AD-022 — User/account lifecycle and notebook ownership

A notebook MUST NOT become ownerless. **Account disablement is immediate** and MUST NOT be blocked merely because the disabled user is a sole notebook owner: disabling blocks new authentication, sessions and user-attributed job/tool dispatch, while solely owned notebooks enter a locked administrative-custody state until ownership is resolved. Final account deletion cannot complete until each solely owned notebook is transferred to another owner or scheduled for deletion under the normal notebook-deletion policy.

Installation administrators MAY perform a narrowly scoped, audited **metadata-only custody operation** to transfer ownership or schedule deletion of an ownerless/sole-disabled-owner notebook. That operation MUST NOT itself grant the administrator notebook-content read access or silently add them as a content member; any separate break-glass content access remains an explicit, separately audited policy. Account deletion removes the user's memberships, private conversations, private Agentic Chat/research/tool traces and private context snapshots/caches (including `StudySessionSnapshot`s), user-scoped provider/connector credentials, preferences and per-user study/view state according to retention policy. Shared notebook content authored by that user MAY remain when the notebook retains it; authorship is represented by a non-login tombstone/identifier rather than preserving active credentials or granting access.

### AD-023 — Derived-content restriction propagation

A generated or transformed object does not become unrestricted merely because its input source was summarized, reformatted or embedded into another artifact. Content-bearing outputs MUST retain version-pinned provenance/dependencies sufficient to compute an effective access/reuse policy. At read/view, copy, share-link creation, download/export and publication time, the authorization layer MUST re-evaluate applicable current notebook ACLs and source/connector restrictions for the material being exposed. A connector MAY explicitly permit transformed/derived output reuse, but that permission must be represented as policy; generation itself is never a laundering boundary.

### AD-024 — Crash-consistent blob lifecycle

The transactional database and a filesystem/object backend do not form one atomic transaction. Blob persistence therefore uses an explicit crash-consistent protocol: write to a non-addressable temporary object, validate size/hash and required durability, finalize it under an immutable opaque/content-derived key, and only then commit a database reference to that final object. A database row MUST NOT reference an unfinished temporary object. Failed DB commits may leave quarantined/orphan blobs, which are reconciled and garbage-collected after a safety interval. Deletion is reference-aware and two-phase: mark/tombstone in transactional state first, then delete unreferenced blob data asynchronously; reconciliation detects missing referenced objects as integrity faults rather than silently treating them as empty content. S3-compatible backends may realize the same contract with backend-appropriate finalize semantics.

### AD-025 — Verifiable technical-specification handoff

The architecture is complete only when its normative behavior can be carried into a technical specification without relying on unstated reviewer knowledge. The technical specification MUST assign stable identifiers to normative requirements and map each to meaningful automated tests, manual tests, documented analysis or an explicit approved deferral. It MUST provide deterministic provider/connector/source fixtures, public-boundary end-to-end coverage and repeatable manual runbooks where human perception, hardware or operator action is the real oracle. Chapter 25 is the authoritative verification/handoff contract; line coverage, a successful code path or an AI agent's self-assessment does not by itself establish conformance.

### AD-026 — Capability applicability and conformance profile

Every technical specification, phase acceptance build and release candidate MUST publish a machine-readable capability/conformance profile identifying implemented, enabled, disabled-optional, provisional and deliberate-non-target behavior plus its required dependencies. Test applicability is derived from that profile: a stable/core capability claimed by the current milestone cannot be marked not applicable; enabling optional code activates its functional, policy, security, privacy, lifecycle and manual tests; provisional/non-target behavior cannot be advertised as parity. Missing optional media/model infrastructure degrades only its declared capability and never silently weakens an enabled capability's contract.

## 4. Implementation choices intentionally left unfrozen

The architecture is complete without freezing technology choices that can be benchmarked or selected during implementation. The following remain implementation/configuration choices rather than unresolved architecture:

- backend programming language/framework;
- frontend framework;
- exact embedding and reranking models;
- web-search provider and browser-automation implementation;
- optional S3-compatible object-store product;
- packaging choice among systemd/native packages and Compose-style deployment;
- installation-specific source/storage/concurrency limits.

These choices MUST conform to the contracts and dependency boundaries in this specification. Their evaluation criteria are summarized in `23-open-questions-adrs.md`.
