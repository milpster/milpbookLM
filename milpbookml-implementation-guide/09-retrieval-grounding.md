# 09 — Retrieval, Grounding and Citation Pipeline

## Query execution

1. Freeze actor, notebook, selected source versions, selected note revisions and conversation context in a manifest.
2. Normalize/query-expand through deterministic logic or a recorded model sub-call.
3. Run lexical and vector retrieval with mandatory notebook/version/authorization filters.
4. Fuse with configurable reciprocal-rank fusion; rerank behind `RerankerProvider` when available.
5. Apply diversity, per-source quotas and token-budget assembly.
6. Generate using evidence IDs, then validate citations before publication.

## Answer contract

The model returns structured answer spans and cited evidence IDs. The server—not the model—resolves source labels/URLs/locators. Unsupported evidence IDs invalidate the draft. Source-only mode must say evidence is insufficient rather than introduce uncited factual claims.

## Citation validator

Validate existence, manifest membership, current read authorization, locator validity and claim/evidence association. Publication is atomic with the final message. Citation jumps resolve the pinned historical version, subject to current authorization and purge state.

## Evaluation

Lock a corpus with relevant evidence judgments, answerability, contradictions and citation entailment. Release reports include recall@k, MRR/nDCG where applicable, citation precision/coverage, unsupported-claim rate and abstention correctness. Thresholds live in the conformance profile and cannot be weakened without review.
