# 15 — PostgreSQL Jobs, Leases and Events

## Schema and claiming

Jobs contain `id`, type, payload schema version/hash, actor, notebook, capability, priority, state, attempts/max-attempts, schedule/deadline, lease owner/expiry, idempotency key, cancellation timestamp/reason, progress, checkpoint, result/error reference and created/updated timestamps. Workers claim with `FOR UPDATE SKIP LOCKED`, set bounded leases and heartbeat. Expired leases are recoverable only for idempotent/resumable handlers; non-reconcilable uncertain external submissions enter an operator-visible state instead of resubmission.

## State machine

`queued -> running -> succeeded|failed|cancelled`; `running -> waiting_external|waiting_capacity|retry_scheduled` are explicit. State transitions use compare-and-swap. Terminal publication and outbox event commit atomically.

## Idempotency

HTTP commands use scoped idempotency keys and request hashes; reuse with a different hash is `409`. Job handlers checkpoint durable stages. Remote provider operation IDs and staged blobs survive worker crashes.

## Outbox/SSE

Domain events enter an outbox in the originating transaction. A dispatcher assigns monotonic per-stream sequence IDs and marks delivery. SSE clients reconnect with `Last-Event-ID`; gaps cause resource resynchronization. Delivery is at-least-once, so consumers deduplicate by event ID.

The versioned event envelope contains `event_id`, `event_type`, schema version, aggregate type/id/version, stream sequence, occurred-at, actor/operation/job IDs, visibility scope and content-free payload or resource reference. Payloads never contain provider credentials or unrestricted source text. Notification projection and SSE use the same durable event identity; a notification failure cannot roll back completed domain work.

## Fairness and authorization

Scheduler quotas prevent one user/notebook/job class from starvation. Revalidate authorization before restricted reads, external dispatch, execution staging, side effects and final publication. Revocation cancels or suppresses further work where practical.

Use separate capacity classes for interactive text, ingestion/indexing, research/browser, execution and media. Weighted fair selection applies per installation/user/notebook; administrator-configured concurrency and cost budgets are checked at enqueue and dispatch. “Generate later” is a durable `waiting_capacity` job with visible reason and cancellation, not an in-memory timer.

## Retention

Compact verbose progress after configured retention while preserving terminal metadata, provenance, disclosure and audit obligations. Notifications never leak notebook titles/content to unauthorized recipients.
