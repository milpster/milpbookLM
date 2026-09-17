# 23 — Implementation ADRs and Remaining Selections

## Resolved for this guide

Stack, packaging and web-research baseline are resolved as TAD-001–TAD-010 in Chapter 00. BrowserOS is excluded from the normative baseline. PostgreSQL FTS is correctly described and BM25 remains a replaceable evaluated enhancement.

## Non-blocking selections

The exact embedding model, reranker, OCR engine, office/PDF parser combination, TTS/STT/image/video providers, reverse proxy and backup utility are deployment-time or phase-specific selections behind frozen interfaces. Each selection requires:

1. license and supply-chain review;
2. capability/quality benchmark on locked fixtures;
3. resource and privacy classification;
4. deterministic adapter fixtures;
5. documented fallback/degraded behavior;
6. an ADR when it changes the reference deployment.

## Decision template

Every ADR states context, decision, alternatives, compatibility/security/privacy consequences, migration/rollback, affected requirement IDs, tests and reconsideration trigger. No remaining item blocks Phase 0 implementation.
