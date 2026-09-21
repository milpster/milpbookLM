# ADR 0002 — pgvector HNSW evaluation: no HNSW index at prototype scale

- Status: accepted (evaluation recorded; HNSW NOT enabled)
- Date: 2026-09-21
- Task: 15 (IDX-01) — "pgvector HNSW only after representative-size evaluation (record evaluation before enabling)"

## Context

The vector arm of retrieval stores `vector(1024)` embeddings (bge-m3, D14)
in `index_chunks.embedding` and sorts by cosine distance. The plan
requires a representative-size evaluation and a recorded decision before
any HNSW index is created. At task-15 scale the scratch corpus holds 9
ready-generation chunks.

## Evaluation

Method: `EXPLAIN (ANALYZE, BUFFERS)` over the exact retrieval query shape
(`ORDER BY embedding <=> query LIMIT k` with the authz filter set), 10
queries per arm, scratch PostgreSQL, schema at 0005:

| arm | median | max | plan |
| --- | --- | --- | --- |
| seqscan (no index) | 0.302 ms | 0.954 ms | `Sort` over full table |
| HNSW index present | 0.156 ms | 0.218 ms | `Sort` over full table |

Recall@10 = 1.0 in both arms (exact kNN over 9 rows). Key observation:
with 9 rows the planner never used the HNSW index even when it existed —
both plans degrade to a full-table sort, so the index bought nothing at
this scale while adding build/memory cost. Report:
`/home/srcds/dev/t15-smoke/hnsw-eval.json`.

## Decision

Do not create an HNSW index at prototype scale. Vector retrieval stays an
exact sequential sort; the over-fetch/retry loop (limits 30 → 100 → 300,
authz filters never dropped) is the mechanism that absorbs under-return,
and it is exactly the behavior HNSW approximation would also feed into.

## Selection field record

1. **License + supply chain**: no new dependency either way (HNSW is an
   index method inside the already-introduced pgvector extension).
2. **Capability/quality benchmark**: numbers above — no planner adoption
   and no recall benefit at 9 vectors; exact sort is already at the
   latency floor that matters (sub-millisecond).
3. **Resource / privacy classification**: HNSW adds graph memory and
   index-build cost per generation swap with no privacy delta; skipping it
   removes both costs.
4. **Deterministic adapter fixtures**: not applicable — performance gate,
   not an adapter; the retrieval query shape is fixed by the authz-in-query
   contract.
5. **Fallback / degraded behavior**: seqscan is the natural degraded mode;
   if HNSW is enabled later and misbehaves, dropping the index returns to
   exactly today's behavior.
6. **Rollback**: `DROP INDEX` — trivial and non-destructive to data.

## Compatibility / security / privacy consequences

None. Authorization-in-query is unchanged in both arms; the evaluation
ran with the production filter set.

## Migration / rollback

Enabling later is a non-destructive `CREATE INDEX ... USING hnsw` in a
future migration; rollback is `DROP INDEX`.

## Affected requirement IDs

ARCH-08 (knowledge_indexing) vector subset; plan line 251 (HNSW gate).

## Tests

- `vector_synonym_hit` QA (semantic near-synonym finds the greeting
  chunk; recall@10 = 1.0 at this scale).
- Over-fetch/retry path exercised by the `under-return` QA checks (limits
  30 → 100 → 300 observed in the QA log).

## Reconsideration trigger

Rerun the evaluation when the representative corpus reaches roughly
10k+ vectors per active generation, or when the vector arm's p50 latency
exceeds ~10 ms in a representative notebook. Re-enable HNSW only if the
planner adopts it and recall@10 stays at the exact-sort baseline within a
recorded tolerance.
