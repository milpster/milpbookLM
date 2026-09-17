# 01 — Vision, Goals, Scope and Product Principles

## 1. Product vision

Build a self-hosted, multi-user research environment for GNU/Linux that can ingest heterogeneous sources, organize them into notebooks, answer questions with verifiable citations, conduct agentic research, create rich derived artifacts, and use both remote and local AI providers without locking the installation to any vendor.

The intended user experience uses the proven **Sources**, **Chat**, and **Studio** notebook pattern seen in the reference product. The project is independent software: the reference product is a behavioral benchmark, not an identity, API, branding or infrastructure dependency.

## 2. Primary goals

The system SHOULD:

1. Reach current Gemini Notebook feature parity wherever technically and legally practical.
2. Work well as a private installation for a small organization or trusted team.
3. Treat local inference as a normal mode, not an unsupported edge case.
4. Preserve source provenance deeply enough to support precise citations and source highlighting.
5. Provide strong reproducibility for generated artifacts.
6. Support agentic web research and controlled code/data analysis.
7. Allow components such as models, vector stores, TTS, STT, image generation and storage backends to be replaced independently.
8. Make performance, model behavior and retrieval behavior observable and benchmarkable.
9. Remain useful when disconnected from paid AI APIs, subject to locally available model capabilities.
10. Preserve clean internal extension boundaries without making a plugin ecosystem a baseline deliverable.

## 3. Non-goals for the initial architecture

The initial architecture does **not** optimize for:

- Internet-scale anonymous public tenancy;
- a fully managed commercial billing platform;
- cross-platform server support;
- a Kubernetes requirement;
- a microVM-per-execution cloud infrastructure;
- compatibility with any vendor's internal/proprietary APIs;
- reproducing proprietary models or exact generation outputs;
- matching another product's plan tiers, quotas or rollout mechanics;
- a native Android/iOS application or mandatory PWA;
- a plugin marketplace/third-party plugin SDK in the parity roadmap;
- coupling authentication, storage, notebooks, sharing or model execution to Google accounts or any other vendor ecosystem.

## 4. Design principles

### 4.1 Source truth before model fluency

A fluent answer without evidence is less valuable than a well-grounded answer. Retrieval and provenance quality are therefore first-order product concerns.

### 4.2 Capability routing instead of vendor routing

Features request capabilities — for example, `text_generation + tools + structured_output + >=128k_context` — rather than asking specifically for one vendor.

### 4.3 Derived state is rebuildable

Embeddings, search indexes, source summaries, thumbnails and caches are derived data. The canonical source snapshot and canonical document representation are the durable foundation.

### 4.4 Artifacts are structured objects

A slide deck is not merely a PDF; an audio overview is not merely an MP3. The structured representation, source evidence, generation recipe and revision history are retained so outputs can be revised and re-rendered.

### 4.5 Long-running work is explicit

OCR, research, transcription, embeddings, video rendering and artifact generation are jobs with state, progress, retry semantics and cancellation.

### 4.6 Local-first does not mean local-only

Remote APIs remain useful, particularly for capabilities unavailable locally. Suitable local providers SHOULD be preferred by default when configured, while external providers remain allowed unless explicitly disabled by installation/notebook policy. The system should permit mixed configurations such as local embeddings + local chat + remote image/video generation. Any content-bearing call to an external provider/service API MUST be disclosed visibly to the initiating user.

### 4.7 Trusted users do not eliminate isolation needs

The audience is ourselves and colleagues, but generated code remains untrusted input. Lightweight local isolation is therefore retained even though a cloud-grade adversarial multi-tenant sandbox is not required.
