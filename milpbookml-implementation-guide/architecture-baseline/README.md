# Self-Hosted Source-Grounded Research Notebook Platform

**System Architecture Specification — v0.10 FINAL**  
**Reference date:** 16 September 2026  
**Target:** GNU/Linux, self-hostable, multi-user, local-first/provider-neutral  
**Status:** Reviewed architecture baseline; no architecture-blocking open questions remain; ready for a separate technical specification.

This specification defines an independent, self-hosted research and knowledge platform. Gemini Notebook / former NotebookLM is used **only as an external behavioral reference** for useful feature parity. The project is **not affiliated with Google** and does not require Google accounts, identity, billing, APIs, storage or models. Provider freedom, local-model support, provenance, observability and self-hosting are first-class requirements; ecosystem features that do not solve a concrete self-hosting need are intentionally deferred.

This package is the authoritative **architecture and product-behavior baseline**, not the implementation technical specification. The next technical-specification phase must choose concrete languages/frameworks/libraries, schemas and endpoint details within these boundaries and satisfy Chapter 25's traceability/testing handoff contract. Those implementation selections are intentionally not invented here.

The central architectural rule is:

> No model vendor, embedding model, search engine, media provider, connector, or storage backend may become part of the notebook domain model.

A notebook remains valid when providers are replaced. Changing an LLM does not rebuild notebook data. Changing embeddings rebuilds only derived indexes. Generated outputs retain immutable input manifests, provenance and generation metadata independently of the provider used to create them.

## Final baseline decisions

- **One self-hosted multi-user installation**, serving one person or a trusted team; no SaaS billing/multi-tenant organization layer.
- **GNU/Linux server target** and one **responsive fully asynchronous web application**; no native mobile client or PWA requirement.
- **No Google/account/ecosystem coupling.** Google documentation is reference material only.
- **Provider-neutral model gateway**, with local/custom providers first-class and OpenAI-compatible endpoints treated as adapters rather than the internal protocol.
- **Suitable local providers preferred by default**; external providers are allowed unless policy disables them and every content-bearing external call is visibly disclosed.
- **OpenCode Big Pickle** is only a replaceable external/bootstrap candidate while it remains available; it is not a dependency.
- **Canonical source representation + provenance** are authoritative; chunks, embeddings and indexes are rebuildable derived state.
- **Hybrid lexical + semantic retrieval + citation validation** underpin ordinary grounded chat. PostgreSQL native FTS is the baseline lexical path; BM25 remains an optional replaceable ranker if evaluation justifies it.
- **Ordinary chat is tool-free and notebook-grounded**; explicit selected notes are version-pinned prompt context. Agentic Chat is a separate tool-capable path.
- **Generic versioned artifact framework** covers reports, tables, mind maps, flashcards/quizzes, slide decks, infographics, Audio/Video Overviews and composite interactive reports.
- **Agentic research + code/data analysis** use an inspectable Agent Runtime and `ExecutionProvider`.
- **Bubblewrap execution** runs under a separate unprivileged identity through a narrow broker, with namespaces/cgroups/no-new-privileges and **no network by default**.
- **Fully asynchronous durable jobs** for ingestion, research and artifact/media generation; closing the browser does not cancel work.
- **Minimal reference infrastructure:** PostgreSQL + PostgreSQL FTS + `pgvector` + PostgreSQL-backed jobs/outbox; blob abstraction backed by local filesystem by default. Blob writes/deletes follow an explicit crash-consistent finalize/reference/reconciliation protocol. Dedicated brokers/search/vector/object stores are optional scale-out substitutions.
- **Local accounts are the auth baseline**; generic OIDC/trusted reverse-proxy auth is optional with an explicit trusted-proxy boundary. No vendor identity is required; personal provider credentials remain private to their owning user.
- **Remote sources are versioned snapshots.** Web URLs refresh manually by default; safe live connectors may auto-refresh using upstream revisions and atomic version activation.
- **Restricted inputs remain restricted through derived outputs.** View/share/copy/export/publication re-evaluate dependency-derived policy; generation cannot launder source permissions.
- **Account disablement is immediate.** Sole-owner notebooks enter locked administrative custody; an audited metadata-only ownership transfer/delete action does not grant admins content access.
- **Deletion distinguishes removal from hard purge.** Hard purge intentionally wins over historical reproducibility and traverses every known content-bearing derivative; backup copies expire under documented finite retention.
- **No baseline plugin marketplace, knowledge graph, Kubernetes, native mobile app, enterprise connector catalog, public API ecosystem, or multi-workspace tenancy.** Internal extension interfaces remain clean so these can be added if justified later.
- **Agent-executable verification is mandatory.** Normative requirements map to automated/manual test ids; deterministic fixtures, canonical browser E2E journeys, perceptual/manual runbooks, CI tiers, AI-evaluation oracles and release evidence are defined in Chapter 25.
- **Capability applicability is explicit.** Every phase/release publishes a conformance profile; stable/core and enabled behavior cannot disappear behind `N/A`, while disabled optional, provisional and deliberate non-target behavior remains honestly classified.
- **Complex multimodal/media workflows are complete architectural citizens.** Provider capabilities, remote async operations, idempotent polling/callback reconciliation, staged recovery, untrusted-binary validation, original/rendition provenance, seekable delivery, safety/refusals and multimodal test oracles cover Audio/Video Overview and provider-generated media.

## Specification chapters

1. [Status, Decisions and Normative Language](00-status-decisions.md)
2. [Vision, Goals, Scope and Product Principles](01-vision-scope.md)
3. [Feature-Parity Target](02-feature-parity-target.md)
4. [Complete Architecture Overview](03-architecture-overview.md)
5. [Deployment Model and GNU/Linux Runtime](04-deployment-linux-multiuser.md)
6. [Domain Model](05-domain-model.md)
7. [Universal Source Ingestion](06-source-ingestion.md)
8. [Canonical Document Model and Provenance](07-canonical-document-provenance.md)
9. [Knowledge Storage and Indexing](08-knowledge-indexing.md)
10. [Retrieval, Grounding and Citations](09-retrieval-grounding.md)
11. [Model Provider Platform](10-model-provider-platform.md)
12. [Agent and Research Runtime](11-agent-research-runtime.md)
13. [Local Isolated Code Execution with Bubblewrap](12-bubblewrap-execution.md)
14. [Studio and Artifact Framework](13-studio-artifacts.md)
15. [Media, Audio, Video and Realtime Interaction](14-media-realtime.md)
16. [Jobs and Orchestration](15-jobs-events.md)
17. [API and Frontend Architecture](16-api-frontend.md)
18. [Authentication, Authorization, Sharing and Collaboration](17-auth-sharing.md)
19. [Observability and Evaluation](18-observability-evaluation.md)
20. [Security, Privacy and Data Governance](19-security-privacy.md)
21. [Internal Extension Boundaries](20-extension-boundaries.md)
22. [Non-Functional Requirements](21-nonfunctional-requirements.md)
23. [Dependency Graph and Implementation Phases](22-dependencies-phases.md)
24. [Architecture Decisions and Implementation Choices](23-open-questions-adrs.md)
25. [Glossary](24-glossary.md)
26. [Software Testing, Release Engineering and Supply Chain](25-software-testing-release-engineering.md)

Also included: [Specification Changelog](CHANGELOG.md), the current [v0.10 Validation Record](REVIEW-v0.10-FINAL.md), and the superseded v0.9 review retained for audit history.

## Verified reference-product baseline

As of 16 September 2026, official Gemini Notebook help documents the stable feature classes used as our parity reference: source-grounded ordinary chat with text/image citations and configurable style/length; a separately documented experimental agentic-chat path with web search/code/file generation; source summaries/Source Guide; heterogeneous file, image, transcribed-audio, EPUB, URL and transcript-backed public-video sources; source labels; collaborative notes and note-to-source conversion; document reports and Interactive Learning Overview; data tables; mind maps; persistent flashcard/quiz study flows; Audio Overviews (Deep Dive, Brief, Critique, Debate and interactive mode); Video Overviews (Explainer, Short, Cinematic); slide decks with revisions and PDF/PPTX export; infographics; source discovery/Deep Research; private/public sharing, notebook copying and artifact links; output-language settings; and asynchronous/background artifact generation. Document/root-level citation fallback is allowed for very short sources, matching the reference product's stated behavior rather than inventing false spans.

Google's 15 September 2026 announcement additionally describes general realtime notebook voice conversations, a mobile audio recorder, notes presented alongside sources for chat/citation/building, editable/new quiz formats and chat follow-up over study performance. Those rollout features remain provisional. Interactive Learning Overview is now documented in the stable Reports help page and is therefore promoted to the Phase 4 parity baseline. Stable FAQ behavior still requires notes to be specifically selected for prompt context, so the announcement is not interpreted as automatic note indexing until documentation changes. The architecture covers the remaining announced capabilities through duplex voice, ordinary audio ingestion, explicit immutable note revisions, extensible study schemas and private immutable study-session snapshots. Native mobile/share-sheet/offline-app behavior remains a deliberate non-target; the responsive web app exposes equivalent core workflows where browsers permit them.

We intentionally do **not** reproduce Google identity, plan tiers, quotas, proprietary connectors, Play Books licensing, cross-product Gemini/Search integrations or native mobile packaging. Their observable behavior may inform generic interfaces, but none is a dependency.

Primary verification sources and rollout caveats are listed in Chapter 02; the validation record is deliberately non-normative.

## Big Pickle caveat

OpenCode currently lists `big-pickle` as a free, limited-time stealth model through an OpenAI-compatible chat-completions endpoint. OpenCode also states that data collected during Big Pickle's free period may be used to improve the model. Consequently Big Pickle is treated as an **external, replaceable and benchmark-required bootstrap/fallback option**, never as a trusted/local default or architectural dependency. Its endpoint, authentication and future availability are configuration, not assumptions embedded in the product.
