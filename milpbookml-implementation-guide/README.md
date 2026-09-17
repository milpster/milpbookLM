# milpbookML Technical Implementation Guideline

Status: v1.2 FINAL implementation-planning handoff derived from architecture v0.10 FINAL.

This package is the normative engineering handoff for a self-hosted, multi-user, source-grounded research notebook. It preserves the architecture's 26-chapter structure. The frozen architecture is included under `architecture-baseline/`; when this guide is silent, the architecture remains authoritative. A conflict is a specification defect and blocks implementation.

## Normative implementation profile

- Backend: Python 3.13 managed with `uv`, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic and psycopg 3.
- Frontend: Node.js 24 LTS, pnpm, React 19, TypeScript, Vite, TanStack Query and Router.
- Persistence: PostgreSQL 18 with `pgvector`; PostgreSQL full-text search; filesystem blob store by default.
- Orchestration: PostgreSQL-backed jobs, leases, outbox and idempotency records.
- Deployment: rootless `podman compose` on GNU/Linux with an explicitly pinned `podman-compose` provider and systemd user-unit integration.
- Research: self-hosted SearXNG discovery, hardened fetch/extraction, Playwright rendering/automation.
- Execution: Bubblewrap plus cgroup v2, no network by default.
- Testing: pytest, Hypothesis, Vitest, Playwright Test, axe-core, deterministic fake providers and golden corpora.

No Google identity, account, billing, API or backend service is required. No Kubernetes, Kafka, Elasticsearch/OpenSearch, standalone vector database, MinIO, plugin marketplace, knowledge graph, native mobile client or BrowserOS dependency is introduced.

## Repository layout

```text
apps/api/                 FastAPI composition root and HTTP/SSE routes
apps/web/                 React application
workers/                  job runners grouped by queue class
packages/domain/          pure entities, policies and state machines
packages/application/     use cases and ports
packages/adapters/        PostgreSQL, blobs, models, parsers, SearXNG, Playwright
packages/contracts/       OpenAPI, JSON Schema, event and provider contracts
infra/podman/             rootless compose, Quadlet/systemd examples
migrations/               Alembic revisions
tests/                    unit, integration, contract, E2E, manual and fixtures
tools/spec/               requirement extraction and conformance checks
```

## Engineering rules

Dependencies point inward: adapters depend on application ports; application depends on the domain; the domain imports no framework or adapter. All public commands carry `request_id`, `actor_id`, `idempotency_key` where applicable and an authorization context. Every content-bearing operation records an immutable input manifest.

Implementation work is accepted only when its requirement IDs, positive and negative tests, migrations, observability and failure semantics are present in `25-software-testing-release-engineering.md`'s ledger.

## Chapters

Files `00`–`25` correspond exactly to architecture chapters `00`–`25`. `CHANGELOG.md`, `REVIEW-FINAL.md` and `MANIFEST-SHA256.txt` describe and verify this package.

Start planning with `PLANNING-HANDOFF.md`, then read `PARITY-SCOPE-AUDIT.md`, `00-status-decisions.md`, `REFERENCE-DEPENDENCIES.md`, the relevant same-numbered architecture/technical chapter pair, and its entries in `requirements.generated.json`. `ARCHITECTURE-CROSS-REFERENCE.md` proves section coverage; `schemas/` validates the machine-readable seeds; `AUDIT-v1.0.md` records the deficiencies corrected after the first implementation-readiness audit.
