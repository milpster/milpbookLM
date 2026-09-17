# 08 — Indexing Implementation

## Storage

Use PostgreSQL tables for chunks, `tsvector`, embeddings and metadata. Create GIN indexes for FTS and pgvector HNSW indexes only after representative-size evaluation. Keep the unindexed canonical document authoritative.

Partition/logically group index rows by immutable `index_generation_id`; rows include notebook, source, source-version, canonical-node/span, language, chunker revision, token count, text checksum and effective restriction discriminator. Retrieval SQL always constrains notebook, active/pinned source versions and authorized source IDs in the query. A second policy check occurs after hydration. Approximate-vector under-return caused by filtered HNSW queries is a recall problem to measure and over-fetch/retry, never a reason to remove authorization filters.

## Chunking

Chunk along canonical structure, preserve tables/lists and retain node/span mappings. Token limits are model-independent configuration with a versioned chunker profile. Never cross source-version boundaries. Record adjacent chunk relationships and section ancestry.

## Lexical and semantic indexes

Use PostgreSQL `websearch_to_tsquery`/language configurations with explicit fallback for unsupported languages; do not label its ranking BM25. Embeddings are produced through `EmbeddingProvider` in deterministic batches and record model/dimension/normalization. Dimension changes create a parallel index generation, never in-place reinterpretation.

Fusion consumes ranked `(chunk_id, score, rank, retriever_id)` lists; normalize only within a retriever and use configurable reciprocal-rank fusion as the reference. Do not compare raw FTS and vector scores directly. Store the fusion/reranker configuration version in every generation manifest.

## Lifecycle

Index rows are built under a generation ID and become queryable only when the source version is activated. Removal immediately filters them; purge deletes them. Rebuild jobs are resumable and swap generations atomically.

## Multimodal evidence

Index OCR, captions and transcripts as derived evidence with locators back to original media. Optional native multimodal vectors use a separate embedding space and cannot silently replace text retrieval.

## Tests

Assert chunk determinism, metadata/ACL filtering, index-generation swaps, multilingual lexical behavior, embedding-dimension rejection and rebuild equivalence.
