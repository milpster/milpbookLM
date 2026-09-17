# 01 — Implementable Scope and Product Rules

## Delivery target

Build one responsive asynchronous web application serving trusted individuals or teams from a GNU/Linux installation. Ordinary notebook chat is source-grounded and tool-free. Agentic Chat is an explicit mode with separately authorized tools and retained run state.

## Enforced boundaries

- Domain objects never contain vendor SDK types.
- Generated artifacts are typed/versioned records, not arbitrary files alone.
- Original bytes and immutable versions are authoritative; indexes and renditions are rebuildable.
- External transmission is blocked until a disclosure event is persisted and surfaced to the initiating user.
- Generated code and untrusted parsers never execute in the API or worker process.
- Responsive browser access is required; native/PWA clients are non-targets.

## Scope control

Every feature PR names a Chapter 02 capability and roadmap phase. Work without such mapping requires an ADR. Infrastructure is added only after measured need; prohibited baseline additions include Kubernetes, Kafka, Elasticsearch/OpenSearch, a separate vector database and MinIO.

## Acceptance

`TECH-01-001`: architecture dependency tests reject imports from domain/application packages into adapters. `TECH-01-002`: ordinary-chat E2E tests prove no tool invocation. `TECH-01-003`: external-provider E2E tests prove pre-dispatch disclosure and retained provider metadata.
