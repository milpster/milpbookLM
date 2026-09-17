# 03 — Complete Architecture Overview

## 1. Layered system map

```mermaid
flowchart TB
    UI[Responsive Async Web Client\nSources | Chat | Studio | Research] --> API[Application API + Streaming]

    API --> AUTHZ[Identity / Policy]
    API --> DOMAIN[Domain Services\nNotebooks | Sources | Conversations | Notes | Artifacts | Sharing]
    AUTHZ --> DOMAIN

    DOMAIN --> INGEST[Ingestion System]
    DOMAIN --> RETRIEVE[Retrieval & Grounding]
    DOMAIN --> AGENT[Agent / Research Runtime]
    DOMAIN --> STUDIO[Studio / Artifact Runtime]

    INGEST --> CANON[Canonical Document + Provenance]
    CANON --> KNOW[Knowledge / Search / Indexing]
    KNOW --> RETRIEVE

    RETRIEVE --> MODELS[Model Platform]
    AGENT --> MODELS
    STUDIO --> MODELS

    AGENT --> TOOLS[Tool Registry]
    TOOLS --> WEB[Web Search / Fetch / Browser]
    TOOLS --> EXEC[ExecutionProvider\nBubblewrap initially]

    STUDIO --> MEDIA[Media Engine]
    STUDIO --> DOCS[Document / Slide Renderer]
    STUDIO --> DATA[Data Analysis Engine]

    DOMAIN --> JOBS[Job Orchestration]
    JOBS --> WORKERS[Worker Pools]

    DOMAIN --> STORE[(Transactional DB)]
    AUTHZ --> STORE
    CANON --> STORE
    KNOW --> INDEX[(Search / Vector Index)]
    INGEST --> OBJECT[(Object Storage)]
    STUDIO --> OBJECT

    MODELS --> DISCLOSE[External-provider Disclosure / Audit]
    DISCLOSE --> UI
    MODELS --> REMOTE[Remote Providers]
    MODELS --> LOCAL[Local Providers\nllama.cpp / vLLM / etc.]

    OBS[Observability + Evaluation] -. traces .-> API
    OBS -. traces .-> RETRIEVE
    OBS -. traces .-> MODELS
    OBS -. traces .-> JOBS
```

## 2. Major bounded contexts

### 2.1 User and notebook domain

Owns users, notebooks, notebook membership, source references, conversations, notes, artifacts and notebook-level configuration. The baseline intentionally has no separate organization/workspace tenancy layer.

### 2.2 Ingestion

Owns importing source bytes/content and producing a canonical normalized representation. Ingestion must be deterministic enough to be re-run and versioned.

### 2.3 Knowledge/indexing

Owns derived searchable representations such as chunks, lexical indexes, embeddings, structural/metadata indexes and retrieval metadata.

### 2.4 Retrieval/grounding

Owns query understanding, candidate retrieval, fusion, reranking, evidence selection, context assembly, claim/evidence mapping and citation validation.

### 2.5 Model platform

Owns provider adapters, model/capability registry, routing, fallbacks, streaming normalization and usage accounting. It enforces provider-policy decisions supplied by the identity/policy boundary and emits external-provider disclosure events.

### 2.6 Agent runtime

Owns multi-step research workflows, tool invocation, state, budgets, cancellation and long-running tasks. It can search/fetch the web, read notebook sources, import sources and invoke the execution provider.

### 2.7 Studio/artifacts

Owns recipes for reports, tables, quizzes, slides, infographics, audio and video, plus artifact versions and rendering. The recipe boundary stays extensible internally without requiring a user-facing plugin system.

### 2.8 Identity and policy

Owns authentication, notebook ACL evaluation, provider/tool policy, connector-supplied source restrictions, public/copy/share rules and policy decisions used by retrieval, agents, artifacts and exports. This boundary is authoritative; models must not decide permissions. Connector-specific access checks are an optional hook inside this boundary, not a separate rights-management platform.

### 2.9 Platform foundation

Owns persistence, object storage, durable jobs/queues, secrets, configuration, audit logs, metrics, notifications and backups. An external event bus is optional, not a baseline dependency.

## 3. Dependency rule

Higher levels MAY depend on lower-level capabilities. Lower levels MUST NOT depend on specific upper-level features.

For example, retrieval returns evidence bundles without knowing whether the consumer is chat, a slide generator, a podcast planner or a research agent.

## 4. Synchronous versus asynchronous paths

Short operations MAY be request/response. Long operations MUST become jobs. The UI receives progress through Server-Sent Events, WebSockets or another streaming mechanism.

Typical synchronous path:

```text
question -> retrieval -> model -> citation validation -> streamed answer
```

Typical asynchronous path:

```text
source upload -> parse -> OCR -> canonicalize -> embed -> index -> ready
```

or:

```text
artifact request -> plan -> gather evidence -> generate -> validate -> render -> ready
```
