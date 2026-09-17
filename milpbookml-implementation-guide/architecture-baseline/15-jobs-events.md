# 15 — Jobs and Orchestration

## 1. Why jobs are core

Many core operations are too expensive or long-running for a single HTTP request: OCR, transcription, embedding, Deep Research, audio/video generation, slide rendering and code analysis.

## 2. Job state model

Required states:

```text
queued
running
waiting
retrying
completed
failed
cancelled
```

Jobs SHOULD expose progress phase, progress fraction when measurable, human-readable status, timestamps and error diagnostics.

## 3. Job classes

- source acquisition/ingestion;
- OCR/STT/enrichment;
- embedding/index build;
- research;
- artifact generation;
- media rendering;
- execution/code analysis;
- export;
- maintenance/rebuild tasks.

## 4. Idempotency

Jobs that modify derived state should be idempotent or use deterministic job keys where feasible. Retry must not create duplicate source versions/artifacts unless version creation is explicitly part of the operation.

Static-input generation/artifact jobs MUST resolve an immutable `GenerationInputManifest` before the corresponding model generation starts. Agentic/research jobs MUST capture an immutable initial run snapshot, then append immutable tool/evidence results; every model generation/synthesis step inside the run receives its own `GenerationInputManifest` containing exactly the evidence available to that step. Ingestion, indexing, export and maintenance jobs instead capture the exact immutable resource/version identifiers and parameters needed for their work. Connector refreshes, source re-indexing, note edits or artifact revisions occurring while a step is running must not silently substitute different `SourceVersion`/`CanonicalDocument`/`NoteRevision`/`ArtifactVersion` inputs. Retry reuses the same logical job/run snapshot and already-committed tool results where safe rather than duplicating side effects; the user must start a new operation to adopt refreshed notebook inputs deliberately.

### 4.1 Client-command idempotency

Retryable mutating API commands that create durable work or resources (for example source import/refresh, research start, artifact generation, export and notebook copy) MUST support a client operation/idempotency key or equivalent command identifier. The key is scoped to the authenticated principal plus command/resource boundary. Repeating the same key with the same canonical request returns the same logical operation/resource result; reusing the key with a materially different request fails explicitly rather than creating ambiguous duplicate work. Idempotency records are retained for a documented retry window and at least until the corresponding operation reaches a stable terminal/resource identity. This API-level contract is separate from worker/job idempotency.

### 4.2 Remote provider jobs and staged media recovery

Jobs invoking a remote asynchronous provider persist the provider operation identity/state described in Chapter 10. Worker restart, timeout or lost HTTP response first reconciles that remote operation; it MUST NOT blindly resubmit a potentially billable image/video job. Callback and poll observations pass through the same idempotent transition function, tolerate duplicates/out-of-order delivery and cannot move a terminal operation back to a running state.

Multi-stage media workflows SHOULD checkpoint immutable validated stage outputs such as evidence plan, script, storyboard, narration segments, accepted provider assets and composed rendition. A retry may reuse a stage only when its input/configuration hash and authorization remain valid. Failed or cancelled stages clean temporary data according to retention policy without deleting an input still referenced by another job. User-visible retry semantics distinguish “resume/reconcile existing provider work” from “start a new generation that may incur new cost.”

## 5. Events

Domain events are useful for decoupling workers, but a separate event-bus product is **not** required initially. A DB-backed durable job queue plus transactional state changes is sufficient for the first implementation. Where events are used, examples include:

```text
SourceCreated
SourceVersionAcquired
CanonicalDocumentCreated
IndexBuildRequested
SourceReady
ResearchStarted
ArtifactRequested
ArtifactGenerated
ArtifactRendered
ExecutionCompleted
```

Events can decouple higher-level workflow orchestration from individual workers.

## 6. Delivery semantics

The baseline job system MUST have durable, retry-safe state transitions. If a separate asynchronous event bus is later introduced, handlers must tolerate at-least-once delivery and duplicate events; use a transactional outbox or equivalent only where a database mutation and external event publication must commit together.

### 6.1 Worker leases and orphan recovery

Long jobs need a lease/heartbeat or equivalent ownership mechanism. If a worker dies, the scheduler must detect orphaned `running` work, release/expire its lease and either retry safely or mark the job failed according to idempotency policy.

### 6.2 Durable message/event metadata

Any durable queue/event message SHOULD carry a stable id, schema version, type, resource/job id, actor/correlation information and only the minimal payload needed by the consumer. Large or sensitive notebook content should be referenced by authorized resource/version id rather than copied into queue messages.

## 7. Cancellation and authorization changes

Long jobs SHOULD be cooperatively cancellable. Subprocesses (browser, FFmpeg, execution environment, model request when supported) must be terminated and temporary resources cleaned up.

Per AD-021, accepting a job does not freeze authorization forever. Workers MUST revalidate the initiating actor's current permission and applicable source/connector restrictions before new content-bearing external dispatch, restricted-source access, execution staging or side effects, and again before publishing/committing a user-visible generated result. A revoked operation SHOULD be cancelled promptly; already-transmitted external data cannot be recalled, but no further dispatch or result exposure is allowed. Pure derived maintenance work owned by the installation (for example rebuilding an index for an otherwise authorized source) uses an explicit system actor rather than impersonating the original user.

## 8. Priority and fairness

A multi-user installation SHOULD prevent one user from monopolizing workers or model endpoints. The scheduler may implement per-user concurrency, priority classes and endpoint-specific queues.

### 8.1 Capacity-aware deferred generation

The scheduler SHOULD support a user-visible `waiting`/deferred state when configured compute/model capacity or policy budgets are temporarily unavailable. A user may choose “generate later”; the job retains the same immutable input manifest, resumes when capacity is available, and notifies the user on completion. This provides the useful behavior of the reference product's deferred generation without copying Google's subscription/quota mechanics.

### 8.2 User-facing completion notifications

Long-running artifacts/research SHOULD emit a user-facing completion event independent of provider disclosure. The web client may surface this as an in-app unread indicator and, with user permission, a browser notification. Notification payloads should contain only the minimum metadata necessary (for example notebook/artifact title and status) and MUST respect current authorization when opened.

## 9. External-provider disclosure events

Long-running/background work may invoke external provider/service APIs after the initiating HTTP request has ended. Jobs MUST therefore carry the initiating user (or system actor), provider locality metadata, and emit a durable disclosure event before content-bearing external dispatch. If the user is connected, the frontend displays the operation-level notification immediately; if not, the disclosure remains visible in job/activity history on the user's next visit. Repeated provider calls inside one job MAY be grouped.

## 10. Frontend updates

Job transitions/progress are streamed to clients through SSE/WebSockets or polled as a fallback. Durable job state in the normal resource API is authoritative; a dropped stream is never interpreted as cancellation or job failure.

For SSE job/activity streams, persisted events SHOULD carry a monotonically ordered per-stream/per-operation event id so clients can reconnect with the last seen id and replay retained transitions. Implementations need not retain every transient progress sample forever: if the requested event has expired, the client resynchronizes from the authoritative job/resource state and then resumes live events. Explicit user cancellation is a command against the durable operation/job, not a side effect of TCP/browser disconnect.
