# 04 — Deployment Model and GNU/Linux Runtime

## 1. Deployment target

The canonical deployment is a single self-hosted installation on GNU/Linux serving multiple authenticated users. It SHOULD run comfortably on one server/workstation while permitting selected workers or model endpoints to live on other LAN hosts. Cluster orchestration is not part of the baseline.

## 2. Logical processes

A practical installation may contain:

- web/API process;
- background worker process(es);
- ingestion/media worker(s);
- optional model gateway process;
- local inference servers managed externally or by the installation;
- database;
- object storage;
- search/vector service if not embedded in the database;
- durable job/queue infrastructure if not implemented directly in the transactional database;
- isolated code-execution helper/launcher.

These are logical roles, not a requirement for one container/process per role.

## 3. Service identities

The deployment MUST use dedicated unprivileged Linux identities. At minimum:

- application/service identity for server and ordinary workers;
- a separate execution identity for model-generated code;
- when browser automation is enabled, a separate unprivileged browser-worker identity/process with no application/provider secrets.

The execution identity MUST NOT possess credentials needed by the application server and MUST NOT own the application's persistent data. The application MUST NOT gain general `sudo`/setuid ability merely to switch identities. The preferred shape is a small local execution-broker service running as the execution identity and accepting narrowly scoped requests over a protected Unix-domain socket or equivalent IPC boundary.

## 4. Packaging

Initial packaging SHOULD favor simple self-hosting. Acceptable implementation directions include:

- native systemd services;
- Podman Compose / Docker Compose;
- distribution packages plus configuration;
- a bundled installer that configures services.

No cluster-orchestration platform is required by the architecture.

## 4.1 Minimal reference deployment

To avoid unnecessary service sprawl, the initial reference deployment SHOULD use PostgreSQL for transactional state, PostgreSQL full-text search plus `pgvector` for the first lexical/vector indexes, and PostgreSQL-backed durable job/lease/outbox tables. Original uploads and large generated media SHOULD use the blob/object abstraction with a local-filesystem backend by default. S3-compatible storage and dedicated search/vector/broker services are scale-out substitutions, not prerequisites.

## 4.2 Blob/transaction consistency

PostgreSQL and a filesystem/object backend do not share a transaction. Storage implementations MUST therefore satisfy AD-024: temporary/unaddressable write -> size/hash validation and required durability -> immutable finalization -> database reference commit. Database state may reference only finalized objects. Orphaned finalized blobs from failed DB commits are quarantined and later garbage-collected; missing referenced blobs are integrity errors surfaced by reconciliation/health tooling. Blob deletion is reference-aware and follows transactional tombstoning before asynchronous physical removal. A local-filesystem implementation SHOULD create the temporary object on the same filesystem as its final store, flush file data/metadata when durable acknowledgement is claimed, finalize with a non-overwriting atomic rename/link/create primitive, and persist the containing directory update before the database reference is committed. S3-compatible backends use backend-appropriate immutable-object/finalization semantics while preserving the same externally visible contract.

## 5. Hardware topology

The architecture MUST support installations where:

- the web application and inference run on the same host;
- inference servers run on separate LAN hosts;
- multiple local model endpoints exist with different GPUs/capabilities;
- remote API models are mixed with local services;
- CPU-only services handle parsing/indexing while GPU hosts handle generation.

## 6. Configuration scopes

Configuration exists at several scopes:

1. installation defaults/policy;
2. user preferences;
3. notebook overrides/policy;
4. per-request advanced options where allowed.

Policy always wins over preference. By default, suitable local providers SHOULD be preferred but external providers remain allowed. An installation or notebook policy can explicitly prohibit external providers even if a user has configured one. Any actual external provider use that transmits notebook/user content must be disclosed to the initiating user.

## 7. Resource management

The installation SHOULD support configurable limits for:

- concurrent model requests;
- concurrent research agents;
- concurrent code executions;
- per-user active jobs;
- upload size;
- notebook storage;
- source count;
- CPU/RAM use for workers;
- GPU endpoint concurrency.

The initial product need not implement billing, but should measure usage so resource limits can be introduced without redesign.

## 8. Health, readiness and feature gates

Services SHOULD expose liveness/readiness information suitable for systemd/Compose/reverse-proxy health checks. Readiness must distinguish hard dependencies (for example transactional storage) from optional/degradable dependencies (for example one unavailable model endpoint). Startup SHOULD fail clearly when required schema migrations, configured blob storage or mandatory secrets are invalid. If isolated execution is enabled, startup/readiness for that capability MUST fail clearly when the execution broker, dedicated execution identity or Bubblewrap prerequisites are invalid; installations with execution disabled MUST remain otherwise usable.

Provider-dependent and optional features SHOULD be controlled through capability discovery and installation/notebook feature gates rather than scattered hard-coded UI assumptions. A feature gate may hide or disable a capability, but it MUST NOT bypass authorization or provider-policy checks.
