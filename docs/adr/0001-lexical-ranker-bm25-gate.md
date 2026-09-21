# ADR 0001 — Lexical ranker BM25 gate: reject dedicated BM25, keep native PostgreSQL FTS

- Status: accepted (gate decision recorded: BM25 adoption REJECTED)
- Date: 2026-09-21
- Task: 15 (IDX-01) micro-index 15.7 (BM25 evaluation gate)

## Context

IDX-01 builds the lexical arm of retrieval on native PostgreSQL full-text
search: per-row `tsvector` (config `english`/`german`, explicit `simple`
fallback per D5), `websearch_to_tsquery`, `ts_rank`, GIN-indexed. The plan's
decision-deadline table gates any BM25 adoption on an evaluation showing
material benefit and requires an adopt-or-reject ADR with the full
selection-field record either way. The baseline constraint stands:
PostgreSQL FTS ranking is intentionally never labeled BM25.

## Decision

Reject adopting a dedicated BM25 ranker. Native PostgreSQL FTS remains the
lexical ranker, unlabeled. A future adoption is additive only (a new
retriever behind the fusion contract).

## Alternatives

1. Dedicated BM25 engine (e.g. tantivy/OpenSearch-class service) as lexical
   ranker.
2. In-application Okapi BM25 computed over chunk text at query time.
3. Native PostgreSQL FTS (chosen — the baseline).

## Selection field record

1. **License + supply chain**: option 3 adds no dependency (PostgreSQL 18 is
   already the mandated store; pgvector already introduced by the vector
   arm). Option 1 adds a heavyweight external engine and a second index to
   keep in sync with index generations; option 2 adds ranking code to the
   API hot path while PG already stores the tsvector.
2. **Capability/quality benchmark (locked fixtures)**: locked prototype
   corpus — all 9 ready-generation chunks (English + German), 5 locked
   queries (`canonical`, `hello world`, `greeting message`, `Provenienz`,
   `Kanonisierung`), mechanical relevance (a chunk is relevant when its
   casefolded text contains every query term). MRR@9 and top-1, never raw
   score magnitudes: PG FTS 0.8 / 0.8; Okapi BM25 (k1=1.5, b=0.75) 0.8 /
   0.8. Identical at prototype scale — no material gain. Report:
    `/home/srcds/dev/milpbookLM/scratch/t15-smoke/bm25-eval.json`.
3. **Resource / privacy classification**: option 3 runs inside the existing
   database process — no extra process, no data leaves the host. Option 1
   is a second networked store (data-egress + availability surface);
   option 2 burns API CPU re-deriving statistics PG already maintains.
4. **Deterministic adapter fixtures**: PG FTS ranking is a pure function of
   (corpus, config, query) and is reproducible under the frozen fixture
   notebook; the BM25 comparison arm is likewise deterministic, which is
   what makes the gate's numbers auditable.
5. **Fallback / degraded behavior**: not applicable to the baseline — FTS
   *is* the lexical ranker; zero-lexical-result queries degrade to the
   vector arm through RRF fusion, and an unknown language falls back to the
   `simple` config at build time.
6. **Rollback**: nothing to roll back (the decision keeps the baseline).
   Reversing a future adoption is a fusion-config change plus dropping the
   added ranker; chunk rows, GIN index, and generations are untouched.

## Compatibility / security / privacy consequences

None. Authorization-in-query is unchanged (retrieval SQL always constrains
notebook + active/pinned versions + authorized sources; the second policy
check runs post-hydration). Per-row `fts_config` is stamped at build time
and recorded in the generation manifest; nothing in the API response
labels the rank BM25 (the fusion manifest note says "native PostgreSQL FTS
ranking (intentionally not labeled BM25)").

## Migration / rollback

No schema migration (0005 is about the chunk primary key, not ranking).
Rollback path as above: additive-only adoption keeps the baseline
recoverable by config.

## Affected requirement IDs

ARCH-08 (knowledge_indexing) lexical subset; D5 language profile
(english + german FTS configs, `simple` fallback, never labeled BM25);
plan micro-index 15.7.1–15.7.3.

## Tests

- Multilingual lexical QA on the live scratch (EN `canonical`; DE
  `Provenienz` plus lowercase `provenienz` — `simple` lowercases, so the
  case-insensitive behavior is verified, not assumed).
- `fused_rrf_shape` (RRF over (chunk_id, score, rank, retriever_id),
  within-retriever normalization only).
- Meta guard: PG FTS ranking is never labeled BM25 in user-facing output.

## Reconsideration trigger

A material MRR/top-1 gain for a BM25-class ranker measured on a
representative-scale locked corpus (NFR seed scale, not the 9-chunk
prototype), including the German subset. Until then the gate stays closed.
