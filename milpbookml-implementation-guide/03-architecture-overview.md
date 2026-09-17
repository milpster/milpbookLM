# 03 — Concrete Architecture

## Runtime components

`api` serves REST/OpenAPI, SSE and the SPA; `worker-core` runs ingestion/indexing/artifact jobs; `worker-media` is optional; `browser-worker` owns Playwright; `execution-worker` owns Bubblewrap; PostgreSQL holds transactional state, vectors, FTS, jobs and outbox; the blob adapter holds immutable bytes.

## Bounded-context modules

`identity`, `notebooks`, `sources`, `canonical`, `indexing`, `retrieval`, `models`, `research`, `execution`, `artifacts`, `jobs`, `policy`, `audit` and `observability` expose application ports. Cross-context calls use application commands/queries or durable events, never direct table access.

## Request paths

Short metadata mutations complete in one database transaction and enqueue follow-up work through the outbox. Long work returns `202` plus a job resource. Streaming tokens are transient presentation; the final message and citation set are committed atomically before `completed` is emitted.

## Dependency enforcement

Use Python import-linter rules and TypeScript project references. SQLAlchemy models live in adapters and map to domain objects; route handlers call use cases only. CI fails cycles and forbidden imports.

## Failure model

All external calls carry deadlines, cancellation and bounded retries. Retryable and terminal errors use stable codes. Partial subsystem failure degrades only declared capabilities and appears in readiness/capability diagnostics.
