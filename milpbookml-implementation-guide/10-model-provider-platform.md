# 10 — Model Provider Platform Implementation

## Ports

Define typed async ports for chat, structured generation, embeddings, reranking, image generation, TTS, STT, video generation and realtime duplex. Requests contain capability requirements, content parts, deadlines, cancellation, disclosure context and immutable manifest ID. Responses contain provider/model revision, usage, finish reason and raw-provider correlation ID.

All ports share an envelope: `request_id`, `operation_id`, actor-owned provider-config reference, model role, exact input-manifest hash, required capabilities, content classification, absolute deadline and idempotency key. Adapters emit normalized lifecycle events (`accepted`, `delta`, `tool_call`, `usage`, `completed`, `refused`, `cancelled`, `failed`) with monotonically increasing local sequence numbers. Raw provider payloads are retained only when policy permits and never substitute for normalized durable metadata.

## Registry and routing

Persist installation providers separately from user credentials. Capability descriptors are probed/validated, then administrator-approved. Routing filters policy, ownership, trust class, modality, context and structured-output support before applying local-first preference, health and cost rules.

## Adapters

Ship an OpenAI-compatible adapter and a native local endpoint adapter first. Big Pickle may be configured as an external OpenAI-compatible candidate but is neither required nor a default when a suitable local route exists. Vendor quirks stay inside adapters.

## Fallback

Fallback never crosses local/external trust policy or user credential ownership. A new provider dispatch triggers authorization revalidation and disclosure. Streaming fallback before visible output is allowed; after visible output it creates an explicit restart, never concatenated providers.

Normalize errors to `invalid_request`, `capability_mismatch`, `auth`, `policy_denied`, `quota`, `rate_limited`, `timeout`, `transport`, `provider_internal`, `malformed_response`, `safety_refusal`, `cancelled` and `uncertain_submission`. Each carries retryability and retry-after where known. Only retry idempotent or safely reconciled operations, with bounded exponential backoff inside the operation deadline.

## Remote media

Persist remote operation ID, safe polling schedule, expiry and staged result state. Webhooks require authenticated signatures and replay protection; polling is always available where provider contracts permit. Cancellation is best-effort and publication still revalidates authorization.

## Tests

Run one reusable compatibility suite against every adapter, plus deterministic fakes for success, streaming interruption, quota, timeout, malformed structured data, safety refusal, cancellation and asynchronous completion.
