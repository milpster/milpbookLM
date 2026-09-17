# 18 — Observability and Evaluation

## 1. Principle

A research system built from retrieval, models and asynchronous pipelines cannot be optimized reliably without traces and repeatable evaluations. Both are first-class components.

## 2. Request tracing

A grounded chat trace should make it possible to inspect:

```text
request
  query interpretation
  lexical retrieval
  vector retrieval
  fusion
  reranking
  context assembly
  model selection/provider
  prompt token count
  time-to-first-token
  generation duration
  citation validation
  final response
```

Agent and artifact traces extend this across tool calls and jobs.

## 3. Metrics

### System
- request latency;
- error rate;
- queue depth;
- worker utilization;
- DB/object-store/search latency;
- job duration/failure/retry rate.

### Models
- request count;
- input/output tokens;
- TTFT;
- generation throughput where available;
- endpoint queueing;
- provider errors;
- cost estimate;
- local GPU endpoint health/capacity.

### Retrieval
- candidate counts;
- retrieval/rerank latency;
- index hit rates;
- evidence sizes;
- context utilization.

## 4. Evaluation corpus

Maintain a versioned benchmark set of notebooks, questions and expected evidence. Include direct lookup, cross-source synthesis, contradiction, table questions, long-document questions and noisy OCR/transcript cases.

## 5. Retrieval metrics

- Recall@k;
- Precision@k;
- MRR/nDCG where appropriate;
- reranker win/loss against baseline;
- source and passage recall.

## 6. Grounding metrics

- citation correctness;
- citation completeness;
- unsupported-claim rate;
- source attribution accuracy;
- contradiction handling;
- source-grounding compliance for ordinary chat;
- when note context is invoked, no unrelated-note leakage and exact `NoteRevision` pinning;
- when study-performance context is invoked, exact `StudySessionSnapshot`/`ArtifactVersion` pinning and no cross-user study-state leakage;
- no-tool/no-web leakage from ordinary chat;
- agentic tool-selection correctness and unnecessary-tool-call rate;
- tool-result provenance/attribution.

## 7. Generation metrics

- task success/usefulness;
- instruction following;
- faithfulness;
- source coverage;
- structured-output validity;
- artifact structural/render validity.

For multimodal artifacts, evaluation additionally covers script/narration faithfulness to selected evidence, visual factual consistency, source-asset attribution, caption/transcript alignment, audio/video synchronization, duration/track/container validity, browser playback compatibility, safety/refusal-policy correctness and graceful fallback when a requested provider capability is unavailable. Provider-generated visual polish does not compensate for unsupported factual claims.

## 7.1 Version-consistency evaluation

Evaluation MUST cover **composite-artifact dependency integrity** (embedded child `ArtifactVersion`s remain stable and reproducible) and **source-refresh race consistency** (a chat/research/artifact operation never mixes source revisions that were not present in its pinned input manifest). These are correctness invariants, not merely quality metrics.

## 8. Provider/model comparison

Evaluation must allow comparing Big Pickle, local models and commercial models on the same notebook workloads. Results should retain model version, quantization/configuration when known, retrieval version and prompt/recipe version.

## 9. Privacy

Tracing must avoid accidentally logging full confidential source content when not required. Configurable redaction/sampling is required for production-like deployments.

## 10. Evaluation protocol and release oracle

Each benchmark release MUST version the corpus, expected evidence, scoring code, prompt/recipe, retrieval/index configuration, provider/model identifier, decoding settings and human rubric. Corpus items are split into development and held-out acceptance sets so prompt/retrieval tuning cannot approve itself on the same examples. Personally identifying or licensed source material requires an explicit retention/use basis; synthetic fixtures are preferred for public CI.

Before a model/provider/retrieval configuration becomes a default, the technical specification MUST define its minimum absolute acceptance thresholds and permitted regression deltas for the metrics relevant to that capability. Exact correctness invariants—citation locator resolution, schema validity, policy compliance, source-selection enforcement and cross-user isolation—require 100% success on their deterministic suites. Quality metrics such as evidence recall, citation completeness, unsupported-claim rate and rubric usefulness use corpus-specific thresholds plus sample counts and uncertainty; no universal numeric value is asserted without the versioned corpus that gives it meaning.

Release comparison MUST include the currently supported baseline configuration. A threshold, scorer, corpus or rubric change is itself versioned and reviewed with before/after results. Failed examples, not only aggregate scores, are retained for diagnosis. Human adjudication records independent scores and a documented disagreement-resolution rule. Chapter 25 defines the execution tiers, nondeterminism policy and evidence retained by CI/release evaluation.
