# 16 — API and Frontend Architecture

## 1. Primary UX model

The web interface centers on a notebook and retains the successful three-surface concept:

- **Sources** — add, label, inspect, enable/disable and navigate sources;
- **Chat** — grounded conversational work;
- **Studio** — generated artifacts and revisions.

Research, source viewer, notebook settings and job/progress views integrate around these surfaces.

A normal interactive session is scoped to one notebook at a time. Cross-notebook retrieval is not implicit; any future multi-notebook feature must be an explicit higher-level operation with its own authorization and input manifest.

## 2. Frontend capabilities

The client should provide:

- notebook navigation;
- drag/drop uploads and URL/source import, plus local source-title editing that does not mutate retained source content;
- optional explicit microphone recording that commits through the normal audio-source ingestion path when browser support/policy permits;
- ingestion/indexing status;
- source labels/categories;
- per-source Source Guide/summary and source viewer with citation highlighting;
- source selection for chat/artifact generation;
- generated notebook/source overview and suggested starting questions;
- streaming ordinary source-grounded chat plus explicit version-pinned note context when that capability is used, and a distinct Agentic Chat mode backed by research/tools/execution;
- chat configuration controls for conversation style (standard/learning/custom) and response length (shorter/default/longer);
- stop/cancel and, where supported, continue/resume controls for in-flight generations;
- per-user private chat history plus reset/delete controls;
- citation hover/jump;
- research progress and candidate-source review;
- Studio artifact browser/viewer/editor (including composite/interactive report rendering, child-artifact navigation, “view generation prompt” metadata and authorized seekable media renditions) plus generate-now/generate-later controls where scheduling requires them, artifact completion/unread indicators and optional browser notifications;
- note editing/version history, save-chat-response-to-note, explicit version-pinned note context where enabled, note transformation, note-to-source conversion and portable export (Markdown/DOCX for document-like notes; CSV/XLSX where a note is tabular and that representation is meaningful);
- study-state UI for flashcards/quizzes;
- explicit private study-performance follow-up that snapshots the requesting user's selected quiz/flashcard session into chat context; announced question add/edit and additional quiz formats remain provisional;
- capability-gated realtime notebook voice chat distinct from Interactive Audio Overview; text fallback remains available;
- notebook-wide custom instructions;
- user-level output-language and appearance (light/dark/device/system) preferences, with feature/artifact language overrides where supported;
- provider/model preferences where allowed;
- a clear local/external provider indicator and operation-level notification whenever notebook/user content is sent to an external provider API;
- sharing/member management, chat-view links, copy permissions and artifact-specific share links;
- system/job diagnostics for administrators.

Download/export UI MUST identify the exact exported version and treat the result as a detached snapshot, not a synchronized editable mirror. Where a generated-media provider refuses, expires or leaves an uncertain remote operation, the UI presents the normalized state and safe retry/reconcile choices rather than implying success or silently submitting a second billable job.

## 3. API style

The baseline transport is deliberately simple:

- versioned HTTP/JSON for resource CRUD and commands;
- Server-Sent Events (SSE) for one-way token/job/progress streams;
- WebSockets only where true bidirectional low-latency transport is required (for example realtime voice, and optionally collaborative-note transport);
- ordinary polling remains a fallback for job state.

The frontend MUST consume the same documented application API rather than depending on private in-process server state. Provider-specific wire formats do not cross this boundary.

## 4. Resource-oriented API

Conceptual resources:

```text
/notebooks
/notebooks/{id}/sources
/notebooks/{id}/conversations
/notebooks/{id}/notes
/notebooks/{id}/artifacts
/notebooks/{id}/research-runs
/jobs
/providers
/models
```

Actions such as source refresh, artifact generation and research start create jobs/resources rather than hiding work in one opaque endpoint.

### 4.1 External automation API (deferred)

The browser application necessarily uses a versioned application API, but a separately supported public automation API and service-account/PAT surface is **not** required for the baseline parity roadmap. If later exposed to non-browser clients, it MUST use revocable scoped credentials and the same notebook authorization layer rather than browser-session assumptions.

## 5. Streaming

Streaming events MAY include:

- model text/reasoning-normalized events;
- tool-call state;
- citations as they become known;
- job status/progress;
- realtime audio events.

The API must not expose provider-specific wire formats directly. Mutating HTTP endpoints require ordinary web security controls (authentication, authorization, CSRF protection where cookie sessions are used, request-size limits and optimistic/version checks where lost updates matter). Retryable commands that create durable resources/work MUST implement the client-command idempotency contract in Chapter 15 so browser/network retries cannot accidentally duplicate imports, research runs, artifacts or exports.

### 5.1 Stream disconnect and reconnect semantics

A streaming generation command MUST establish a server-side operation/message identity before or as generation begins. Loss of the HTTP/SSE/WebSocket connection does **not** imply user cancellation. Unless the user explicitly cancels, the server may continue the already-authorized generation and commit the final `Message`/operation result according to normal policy.

On reconnect, the client resolves the operation/message resource and resumes from retained stream events when available. If token-level replay is unavailable or its bounded replay buffer has expired, the client falls back to the persisted partial/final operation state rather than starting a duplicate generation. Continuing a generation after an actual server-side failure is an explicit continuation/retry action with defined manifest semantics, not an accidental reconnect behavior. Durable background jobs follow Chapter 15's event-id/reconciliation contract.

## 6. Source viewer

The source viewer is architecturally important because citations resolve to canonical locations. It should support PDF page/highlight, transcript timestamp, spreadsheet range and webpage/block navigation.

## 7. Responsive asynchronous web application

The product is a single fully asynchronous web application. There is no separate native Android/iOS client in the target architecture. The same browser application MUST adapt responsively to desktop, tablet and phone form factors. PWA installation/offline application behavior is not a baseline requirement.

All long-running operations remain server-side asynchronous jobs. Browser clients reconnect to job state through the normal API/streaming mechanisms; closing or navigating away from the page must not cancel durable work unless the user explicitly cancels it.
