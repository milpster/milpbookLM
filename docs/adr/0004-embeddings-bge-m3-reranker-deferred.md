# ADR 0004 — Embeddings: bge-m3 Q8_0; dedicated reranker deferred

- Status: accepted (embedding); explicitly deferred (reranker)
- Date: 2026-09-21
- Task: 19 (MOD-01b), ARCH-23-001..004

## Context

D14 already deployed bge-m3 on CPU for multilingual retrieval. Task 19 must
freeze that selection against corpus v1 and either select a reranker or record
an explicit degraded mode. Current retrieval already uses deterministic RRF.

## Decision

Select `/home/srcds/ai/ai/bge-m3-Q8_0.gguf` for local DE/EN embeddings at
dimension 1024. Defer a dedicated reranker. The reference retrieval path stays
lexical plus bge-m3 vector candidates fused by RRF only.

## Alternatives

1. multilingual-e5-small: smaller, but not deployed and would be a quality
   trade plus a prohibited acquisition.
2. GPU bge-m3: unnecessary for the measured prototype and would consume chat
   capacity.
3. Dedicated cross-encoder reranker: deferred until a locked-corpus win
   justifies its latency, memory, license, and lifecycle cost.

## Selection record

1. **License and supply chain**: bge-m3 is distributed under MIT terms; the
   existing Q8_0 GGUF is pinned at SHA-256
   `950f4a8e5e19477a6d3c26d2f162233c20002c601f75e4b002e3239997821167`.
   No artifact was acquired in task 19.
2. **Version/digest and capability/quality benchmark**: bge-m3 Q8_0 digest
   above, llama.cpp OpenAI-compatible embedding surface, fixed output dimension
   1024. EVAL-GATE-001 embedded 40 locked judgments plus 40 candidate chunks
   and achieved recall@3 overall 1.0, German 1.0, English 1.0 against minima
   0.95/0.90/0.90.
3. **Hardware/resource envelope and privacy class**: CPU-only (`-ngl 0`), four
   threads, context 8192, loopback endpoint `127.0.0.1:8010`; local/private,
   with no content egress and no chat-GPU allocation.
4. **Deterministic fake**: the existing deterministic embedding adapter fake
   remains the software-test oracle. Corpus v1, hashes, expected chunk IDs,
   dimension, cosine scoring, and thresholds are locked in
   `tests/evaluation/`; the live report records the real adapter result.
5. **Fallback/degraded behavior**: an unavailable embedding endpoint degrades
   retrieval to the lexical arm; no fabricated vector scores are emitted. A
   missing reranker degrades to versioned RRF-only fusion, which is the selected
   prototype behavior rather than an error.
6. **Rollback**: return to lexical-only retrieval without changing canonical
   data. Any embedding replacement builds a parallel generation and must pass
   dimension and corpus gates before atomic activation; never write a new
   dimension into the active generation in place.

## Compatibility, security and privacy consequences

The 1024-dimensional index contract remains unchanged. Canonical documents do
not contain model-specific fields; embeddings are rebuildable derived data.
CPU locality preserves the local-private classification.

## Migration / rollback

No schema migration. Re-embedding uses a parallel index generation. Reranker
adoption would be an additive provider role and a new reviewed benchmark.

## Affected requirement IDs and tests

ARCH-23-001..004, ARCH-08 embedding-generation subset, ARCH-09 retrieval
subset, ARCH-18 evaluation subset, D14, and EVAL-GATE-001 v1.

## Reconsideration trigger

Reconsider bge-m3 if recall falls below a locked threshold, CPU latency blocks
indexing, or model/license provenance changes. Reconsider the reranker when a
representative corpus demonstrates a material win over RRF after latency and
resource costs.
