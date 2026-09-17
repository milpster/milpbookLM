# 10 — Model Provider Platform

## 1. Goal

Provide a stable internal AI capability API independent of any provider. Big Pickle, local Qwen via llama.cpp, and any optionally configured commercial/open gateways are adapters behind this layer; no vendor is structurally privileged.

## 2. Internal model concepts

### Provider
A configured service endpoint plus authentication and policy metadata.

### Model
A concrete model exposed by a provider.

### Capability descriptor
Machine-readable claims about input/output modes and operational features.

### Model role
A logical application purpose such as `chat`, `research`, `query_rewrite`, `reranker`, `embedding`, `vision`, `stt`, `tts`, `realtime_voice`, `image_generation`, `video_generation`, or `fast_background`. Roles should only be added when they produce a real routing/policy distinction; they are not a taxonomy of every internal task.

## 3. Capability descriptor

Conceptual fields:

```yaml
provider: local-llamacpp
model: qwen-example
inputs: [text]
outputs: [text, structured_json]
tools: true
reasoning: true
streaming: true
context_window: 262144
max_output_tokens: 32768
features:
  grammar: true
  prefix_cache: true
media:
  input_formats: []
  output_formats: []
  aspect_ratios: []
  resolutions: []
  duration_range_seconds: null
  synchronous: true
  asynchronous_job: false
  supports_cancel: true
  supports_revision: false
privacy:
  location: local
  retention: none
  training_use: false
```

Capability data may be discovered, configured or overridden by an administrator. Adapters SHOULD support capability probes/conformance tests because provider-advertised features are not always reliable. Context budgeting must account for provider/model tokenization or a safe approximation rather than assuming one universal tokenizer.

For vision, speech, image and video capabilities, the descriptor MUST be able to express applicable MIME/container/codec families, dimensions/resolution, aspect ratio, duration/sample/frame limits, languages/voices, style or steering controls, number/size of input assets, synchronous versus remote asynchronous operation, cancellation/revision support, safety/refusal behavior, provider-side retention and returned provenance/watermark metadata. A provider may expose only a subset; unsupported combinations fail capability negotiation before content dispatch rather than being guessed from a model name.

## 4. Internal request protocol

The application SHOULD normalize:

- messages/content parts;
- system/developer instructions;
- tool definitions/calls/results;
- structured-output schema;
- reasoning controls where supported;
- generation parameters;
- multimodal inputs;
- streaming events;
- usage accounting;
- errors/retryability.

Provider-specific fields may be carried in an extension namespace but must not leak into domain services. Request/response metadata SHOULD retain the provider-reported model/version/fingerprint where available because aliases and hosted model implementations may change over time.

## 4.1 Realtime/duplex capability

Realtime voice is not always reducible to a sequence of ordinary HTTP chat-completion calls. The model platform SHOULD expose a provider-neutral long-lived duplex session capability for native live-audio models while retaining a composable fallback (`streaming STT -> LLM -> streaming TTS`). Capability metadata must advertise interruption/barge-in, streaming input/output modalities, session duration/limits and whether transcripts/audio are retained by the provider.

## 4.2 Remote asynchronous media operations

Image/video providers may return a remote operation id instead of a completed asset. The internal provider contract MUST normalize submit, observe/poll, optional authenticated callback, cancel where supported, terminal success/failure/refusal, result acquisition and expiry. It records the local job id, provider operation id, exact request/input-manifest hash, provider/account scope and last authoritative remote state without exposing credentials to the domain.

Submission uses a provider idempotency key when supported. If submission outcome is unknown, the adapter reconciles by that key or provider operation id before issuing another billable generation. Polling and callbacks are two delivery mechanisms for the same state machine: duplicate/out-of-order notifications are safe, terminal state is monotonic, and a callback alone is not trusted as authorization to publish content. Providers lacking safe reconciliation MUST surface the uncertain state for operator/user resolution rather than silently resubmit an expensive job.

## 5. Provider adapters

Baseline adapter classes:

- a generic OpenAI-compatible HTTP adapter, usable for compatible local servers and external gateways such as OpenCode;
- native adapters only when a required capability cannot be represented faithfully through the generic protocol;
- capability-specific adapters for embeddings/reranking, STT/TTS and media generation where those services use different protocols.

Provider presets/configuration MAY supply known endpoint/model defaults, but a separate provider-specific adapter is not required merely because a service has a different base URL or authentication setting.

## 6. Big Pickle baseline

OpenCode currently lists `big-pickle` as a **free, limited-time stealth model** and exposes it through an OpenAI-compatible chat-completions endpoint. The adapter MUST treat endpoint and authentication as configuration and MUST NOT encode a permanent account, pricing, availability or URL assumption. Big Pickle is an **external bootstrap/fallback candidate**, not a local dependency, and its suitability for research/chat must be measured on the project's notebook evaluation corpus rather than inferred from its availability as a coding-oriented gateway model. When a suitable local provider exists, local-first routing remains the default.

OpenCode also states that during Big Pickle's free period, collected data may be used to improve the model. Therefore the provider registry must expose a **trust/privacy classification** and external/local flag. External providers are allowed by default but routing must be able to exclude them when installation/notebook policy explicitly requires local-only processing.

Reference: https://opencode.ai/docs/zen. The adapter treats endpoint + auth mode as versioned configuration so a provider-side change does not require a domain change.

## 7. Routing

A role request may specify required capabilities:

```text
text input
structured output
tool calling
context >= 100k
privacy <= configured trust boundary
```

The router selects from allowed providers/models based on administrator/user preference, availability, capability, latency/cost policy and fallback order. Provider locality/trust classification (`local`, administrator-designated trusted-network, or `external`) is configuration/policy metadata, not inferred solely from hostname. Default configuration SHOULD prefer a suitable local provider when one is available. Before or at dispatch of an operation that transmits user/notebook content to an external provider/service (including hosted LLM, embedding, reranking, speech, media-generation or search capabilities), the frontend MUST receive an external-provider disclosure event containing at least provider, model/capability role and operation identity. This is a notification requirement, not a confirmation requirement, unless a stricter policy is configured.

## 8. Local inference

Local endpoints are first-class. Multiple endpoints MAY be registered, including different machines/GPUs. Endpoint health, queue depth and capacity should be observable so routing can avoid overloaded instances.

## 9. Failure, cancellation and fallback

Adapters SHOULD normalize provider rate limits, retry-after hints, transient versus permanent errors, request cancellation and timeout behavior. The gateway SHOULD support bounded exponential backoff, endpoint health/circuit-breaking and per-provider concurrency/rate budgets so a failing provider does not cause retry storms.

Fallback SHOULD be explicit and policy-aware. Local-to-external fallback is allowed by default, but MUST trigger the same external-provider disclosure as an explicitly selected remote model. A request must never fall back to an external provider when installation/notebook policy forbids external data transfer.

## 10. Cost and quota controls

Provider/model metadata SHOULD expose price/usage accounting where available. Installation/user budgets and hard/soft limits MAY be applied independently of provider billing. Free or zero-priced models must still be treated as quota-limited external dependencies whose availability can change.

## 11. Provider credentials

Credentials are secrets, never stored in notebook content or plaintext database fields. They may be installation- or user-scoped and are decrypted/read only inside the model gateway/adapter boundary using the installation secret mechanism described in Chapter 19. Installation-scoped credentials may be used by authorized users according to policy. A user-scoped credential is private to its owner and MUST NOT be used for another user's operation, public/anonymous traffic, or shared background work attributed to somebody else. Notebook defaults therefore reference only installation-scoped/shared provider configurations; an individual user can apply their own permitted personal provider to operations they initiate. Credentials MUST be redacted from logs/traces and support rotation/revocation. User-configurable provider base URLs must be subject to installation policy/validation so the model-provider feature cannot become an unintended SSRF path to privileged local services.
