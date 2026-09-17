# Architecture-to-Implementation Cross-Reference

This index maps every heading in the frozen v0.10 FINAL architecture to its implementation chapter and to the occurrence-level requirement records sourced from that section. The frozen text remains authoritative; the implementation chapter supplies concrete technology, component, data, security and verification decisions. A section with no requirement IDs is contextual rather than silently omitted.

| Architecture section | Technical destination | Requirement records |
| --- | --- | --- |
| `architecture-baseline/00-status-decisions.md:1` — 00 — Status, Decisions and Normative Language | `00-status-decisions.md` | Context only |
| `architecture-baseline/00-status-decisions.md:3` — 1. Purpose | `00-status-decisions.md` | `ARCH-00-001` |
| `architecture-baseline/00-status-decisions.md:7` — 2. Normative terms | `00-status-decisions.md` | `ARCH-00-002`, `ARCH-00-003`, `ARCH-00-004`, `ARCH-00-005`, `ARCH-00-006`, `ARCH-00-007`, `ARCH-00-008`, `ARCH-00-009`, `ARCH-00-010`, `ARCH-00-011`, `ARCH-00-012` |
| `architecture-baseline/00-status-decisions.md:17` — 3. Resolved architecture decisions | `00-status-decisions.md` | Context only |
| `architecture-baseline/00-status-decisions.md:19` — AD-001 — Deployment model | `00-status-decisions.md` | Context only |
| `architecture-baseline/00-status-decisions.md:23` — AD-002 — Operating-system target | `00-status-decisions.md` | Context only |
| `architecture-baseline/00-status-decisions.md:27` — AD-003 — Provider neutrality | `00-status-decisions.md` | `ARCH-00-013` |
| `architecture-baseline/00-status-decisions.md:31` — AD-004 — Initial LLM candidate | `00-status-decisions.md` | `ARCH-00-014`, `ARCH-00-015` |
| `architecture-baseline/00-status-decisions.md:35` — AD-005 — Local models | `00-status-decisions.md` | `ARCH-00-016`, `ARCH-00-017` |
| `architecture-baseline/00-status-decisions.md:39` — AD-006 — Provenance-first knowledge architecture | `00-status-decisions.md` | `ARCH-00-018`, `ARCH-00-019` |
| `architecture-baseline/00-status-decisions.md:43` — AD-007 — Generic artifact system | `00-status-decisions.md` | Context only |
| `architecture-baseline/00-status-decisions.md:47` — AD-008 — Agent separation | `00-status-decisions.md` | `ARCH-00-020` |
| `architecture-baseline/00-status-decisions.md:51` — AD-009 — Code execution | `00-status-decisions.md` | Context only |
| `architecture-baseline/00-status-decisions.md:55` — AD-010 — Evaluation and observability | `00-status-decisions.md` | `ARCH-00-021` |
| `architecture-baseline/00-status-decisions.md:59` — AD-011 — External-provider default policy and disclosure | `00-status-decisions.md` | `ARCH-00-022`, `ARCH-00-023`, `ARCH-00-024` |
| `architecture-baseline/00-status-decisions.md:64` — AD-012 — Execution networking | `00-status-decisions.md` | `ARCH-00-025`, `ARCH-00-026`, `ARCH-00-027` |
| `architecture-baseline/00-status-decisions.md:69` — AD-013 — Product and identity independence | `00-status-decisions.md` | `ARCH-00-028` |
| `architecture-baseline/00-status-decisions.md:73` — AD-014 — Single-installation user/notebook scope | `00-status-decisions.md` | Context only |
| `architecture-baseline/00-status-decisions.md:76` — AD-015 — Remote-source refresh semantics | `00-status-decisions.md` | `ARCH-00-029` |
| `architecture-baseline/00-status-decisions.md:80` — AD-016 — Removal, deletion and purge | `00-status-decisions.md` | `ARCH-00-030`, `ARCH-00-031` |
| `architecture-baseline/00-status-decisions.md:88` — AD-017 — Minimal reference persistence/orchestration stack | `00-status-decisions.md` | `ARCH-00-032` |
| `architecture-baseline/00-status-decisions.md:92` — AD-018 — Authentication baseline | `00-status-decisions.md` | `ARCH-00-033` |
| `architecture-baseline/00-status-decisions.md:96` — AD-019 — Provider configuration scopes | `00-status-decisions.md` | `ARCH-00-034`, `ARCH-00-035` |
| `architecture-baseline/00-status-decisions.md:100` — AD-020 — Personal provider credential isolation | `00-status-decisions.md` | `ARCH-00-036` |
| `architecture-baseline/00-status-decisions.md:104` — AD-021 — Authorization revalidation for asynchronous work | `00-status-decisions.md` | `ARCH-00-037`, `ARCH-00-038`, `ARCH-00-039` |
| `architecture-baseline/00-status-decisions.md:108` — AD-022 — User/account lifecycle and notebook ownership | `00-status-decisions.md` | `ARCH-00-040`, `ARCH-00-041`, `ARCH-00-042` |
| `architecture-baseline/00-status-decisions.md:114` — AD-023 — Derived-content restriction propagation | `00-status-decisions.md` | `ARCH-00-043`, `ARCH-00-044`, `ARCH-00-045` |
| `architecture-baseline/00-status-decisions.md:118` — AD-024 — Crash-consistent blob lifecycle | `00-status-decisions.md` | `ARCH-00-046` |
| `architecture-baseline/00-status-decisions.md:122` — AD-025 — Verifiable technical-specification handoff | `00-status-decisions.md` | `ARCH-00-047`, `ARCH-00-048` |
| `architecture-baseline/00-status-decisions.md:126` — AD-026 — Capability applicability and conformance profile | `00-status-decisions.md` | `ARCH-00-049` |
| `architecture-baseline/00-status-decisions.md:130` — 4. Implementation choices intentionally left unfrozen | `00-status-decisions.md` | `ARCH-00-050` |
| `architecture-baseline/01-vision-scope.md:1` — 01 — Vision, Goals, Scope and Product Principles | `01-vision-scope.md` | Context only |
| `architecture-baseline/01-vision-scope.md:3` — 1. Product vision | `01-vision-scope.md` | Context only |
| `architecture-baseline/01-vision-scope.md:9` — 2. Primary goals | `01-vision-scope.md` | `ARCH-01-001` |
| `architecture-baseline/01-vision-scope.md:24` — 3. Non-goals for the initial architecture | `01-vision-scope.md` | Context only |
| `architecture-baseline/01-vision-scope.md:40` — 4. Design principles | `01-vision-scope.md` | Context only |
| `architecture-baseline/01-vision-scope.md:42` — 4.1 Source truth before model fluency | `01-vision-scope.md` | Context only |
| `architecture-baseline/01-vision-scope.md:46` — 4.2 Capability routing instead of vendor routing | `01-vision-scope.md` | Context only |
| `architecture-baseline/01-vision-scope.md:50` — 4.3 Derived state is rebuildable | `01-vision-scope.md` | Context only |
| `architecture-baseline/01-vision-scope.md:54` — 4.4 Artifacts are structured objects | `01-vision-scope.md` | Context only |
| `architecture-baseline/01-vision-scope.md:58` — 4.5 Long-running work is explicit | `01-vision-scope.md` | Context only |
| `architecture-baseline/01-vision-scope.md:62` — 4.6 Local-first does not mean local-only | `01-vision-scope.md` | `ARCH-01-002`, `ARCH-01-003`, `ARCH-01-004` |
| `architecture-baseline/01-vision-scope.md:66` — 4.7 Trusted users do not eliminate isolation needs | `01-vision-scope.md` | Context only |
| `architecture-baseline/02-feature-parity-target.md:1` — 02 — Feature-Parity Target | `02-feature-parity-target.md` | Context only |
| `architecture-baseline/02-feature-parity-target.md:3` — 1. Reference product | `02-feature-parity-target.md` | Context only |
| `architecture-baseline/02-feature-parity-target.md:7` — 2. User-facing parity matrix | `02-feature-parity-target.md` | Context only |
| `architecture-baseline/02-feature-parity-target.md:55` — 3. Supported source families | `02-feature-parity-target.md` | `ARCH-02-001`, `ARCH-02-002` |
| `architecture-baseline/02-feature-parity-target.md:78` — 3.1 Parity behaviors that are product-specific rather than architectural constraints | `02-feature-parity-target.md` | `ARCH-02-003` |
| `architecture-baseline/02-feature-parity-target.md:86` — 3.2 Ordinary chat versus agentic chat | `02-feature-parity-target.md` | `ARCH-02-004`, `ARCH-02-005`, `ARCH-02-006` |
| `architecture-baseline/02-feature-parity-target.md:92` — 4. Feature equivalence versus implementation equivalence | `02-feature-parity-target.md` | Context only |
| `architecture-baseline/02-feature-parity-target.md:101` — 5. Explicitly superior target behaviors | `02-feature-parity-target.md` | `ARCH-02-007` |
| `architecture-baseline/02-feature-parity-target.md:117` — 6. Reference-documentation caveat | `02-feature-parity-target.md` | Context only |
| `architecture-baseline/02-feature-parity-target.md:121` — 7. Upstream references | `02-feature-parity-target.md` | Context only |
| `architecture-baseline/03-architecture-overview.md:1` — 03 — Complete Architecture Overview | `03-architecture-overview.md` | Context only |
| `architecture-baseline/03-architecture-overview.md:3` — 1. Layered system map | `03-architecture-overview.md` | Context only |
| `architecture-baseline/03-architecture-overview.md:55` — 2. Major bounded contexts | `03-architecture-overview.md` | Context only |
| `architecture-baseline/03-architecture-overview.md:57` — 2.1 User and notebook domain | `03-architecture-overview.md` | Context only |
| `architecture-baseline/03-architecture-overview.md:61` — 2.2 Ingestion | `03-architecture-overview.md` | `ARCH-03-001` |
| `architecture-baseline/03-architecture-overview.md:65` — 2.3 Knowledge/indexing | `03-architecture-overview.md` | Context only |
| `architecture-baseline/03-architecture-overview.md:69` — 2.4 Retrieval/grounding | `03-architecture-overview.md` | Context only |
| `architecture-baseline/03-architecture-overview.md:73` — 2.5 Model platform | `03-architecture-overview.md` | Context only |
| `architecture-baseline/03-architecture-overview.md:77` — 2.6 Agent runtime | `03-architecture-overview.md` | Context only |
| `architecture-baseline/03-architecture-overview.md:81` — 2.7 Studio/artifacts | `03-architecture-overview.md` | Context only |
| `architecture-baseline/03-architecture-overview.md:85` — 2.8 Identity and policy | `03-architecture-overview.md` | `ARCH-03-002` |
| `architecture-baseline/03-architecture-overview.md:89` — 2.9 Platform foundation | `03-architecture-overview.md` | Context only |
| `architecture-baseline/03-architecture-overview.md:93` — 3. Dependency rule | `03-architecture-overview.md` | `ARCH-03-003` |
| `architecture-baseline/03-architecture-overview.md:99` — 4. Synchronous versus asynchronous paths | `03-architecture-overview.md` | `ARCH-03-004` |
| `architecture-baseline/04-deployment-linux-multiuser.md:1` — 04 — Deployment Model and GNU/Linux Runtime | `04-deployment-linux-multiuser.md` | Context only |
| `architecture-baseline/04-deployment-linux-multiuser.md:3` — 1. Deployment target | `04-deployment-linux-multiuser.md` | `ARCH-04-001` |
| `architecture-baseline/04-deployment-linux-multiuser.md:7` — 2. Logical processes | `04-deployment-linux-multiuser.md` | Context only |
| `architecture-baseline/04-deployment-linux-multiuser.md:24` — 3. Service identities | `04-deployment-linux-multiuser.md` | `ARCH-04-002`, `ARCH-04-003`, `ARCH-04-004`, `ARCH-04-005` |
| `architecture-baseline/04-deployment-linux-multiuser.md:34` — 4. Packaging | `04-deployment-linux-multiuser.md` | `ARCH-04-006` |
| `architecture-baseline/04-deployment-linux-multiuser.md:45` — 4.1 Minimal reference deployment | `04-deployment-linux-multiuser.md` | `ARCH-04-007`, `ARCH-04-008` |
| `architecture-baseline/04-deployment-linux-multiuser.md:49` — 4.2 Blob/transaction consistency | `04-deployment-linux-multiuser.md` | `ARCH-04-009`, `ARCH-04-010` |
| `architecture-baseline/04-deployment-linux-multiuser.md:53` — 5. Hardware topology | `04-deployment-linux-multiuser.md` | `ARCH-04-011` |
| `architecture-baseline/04-deployment-linux-multiuser.md:63` — 6. Configuration scopes | `04-deployment-linux-multiuser.md` | `ARCH-04-012`, `ARCH-04-013` |
| `architecture-baseline/04-deployment-linux-multiuser.md:74` — 7. Resource management | `04-deployment-linux-multiuser.md` | `ARCH-04-014`, `ARCH-04-015` |
| `architecture-baseline/04-deployment-linux-multiuser.md:90` — 8. Health, readiness and feature gates | `04-deployment-linux-multiuser.md` | `ARCH-04-016`, `ARCH-04-017`, `ARCH-04-018`, `ARCH-04-019`, `ARCH-04-020`, `ARCH-04-021`, `ARCH-04-022` |
| `architecture-baseline/05-domain-model.md:1` — 05 — Domain Model | `05-domain-model.md` | Context only |
| `architecture-baseline/05-domain-model.md:3` — 1. Root object graph | `05-domain-model.md` | Context only |
| `architecture-baseline/05-domain-model.md:28` — 2. User | `05-domain-model.md` | Context only |
| `architecture-baseline/05-domain-model.md:32` — 3. NotebookMembership | `05-domain-model.md` | Context only |
| `architecture-baseline/05-domain-model.md:36` — 4. Notebook | `05-domain-model.md` | `ARCH-05-001`, `ARCH-05-002` |
| `architecture-baseline/05-domain-model.md:53` — 5. Source and SourceVersion | `05-domain-model.md` | `ARCH-05-003`, `ARCH-05-004` |
| `architecture-baseline/05-domain-model.md:59` — 6. Conversation and Message | `05-domain-model.md` | `ARCH-05-005`, `ARCH-05-006` |
| `architecture-baseline/05-domain-model.md:63` — 7. Note and NoteRevision | `05-domain-model.md` | `ARCH-05-007`, `ARCH-05-008`, `ARCH-05-009`, `ARCH-05-010`, `ARCH-05-011` |
| `architecture-baseline/05-domain-model.md:73` — 8. Artifact and ArtifactVersion | `05-domain-model.md` | Context only |
| `architecture-baseline/05-domain-model.md:77` — 8.1 UserArtifactState / study progress | `05-domain-model.md` | `ARCH-05-012`, `ARCH-05-013`, `ARCH-05-014` |
| `architecture-baseline/05-domain-model.md:83` — 9. GenerationInputManifest | `05-domain-model.md` | `ARCH-05-015`, `ARCH-05-016` |
| `architecture-baseline/05-domain-model.md:101` — 10. ResearchRun | `05-domain-model.md` | Context only |
| `architecture-baseline/05-domain-model.md:105` — 10.1 RunEvidenceSnapshot | `05-domain-model.md` | `ARCH-05-017`, `ARCH-05-018`, `ARCH-05-019`, `ARCH-05-020` |
| `architecture-baseline/05-domain-model.md:111` — 11. Separation invariants | `05-domain-model.md` | Context only |
| `architecture-baseline/06-source-ingestion.md:1` — 06 — Universal Source Ingestion | `06-source-ingestion.md` | Context only |
| `architecture-baseline/06-source-ingestion.md:3` — 1. Responsibility | `06-source-ingestion.md` | Context only |
| `architecture-baseline/06-source-ingestion.md:7` — 2. Input adapters | `06-source-ingestion.md` | `ARCH-06-001` |
| `architecture-baseline/06-source-ingestion.md:11` — File sources | `06-source-ingestion.md` | Context only |
| `architecture-baseline/06-source-ingestion.md:23` — Network sources | `06-source-ingestion.md` | Context only |
| `architecture-baseline/06-source-ingestion.md:28` — Connector sources | `06-source-ingestion.md` | `ARCH-06-002` |
| `architecture-baseline/06-source-ingestion.md:36` — Internal/generated sources | `06-source-ingestion.md` | Context only |
| `architecture-baseline/06-source-ingestion.md:41` — 3. Ingestion stages | `06-source-ingestion.md` | `ARCH-06-003` |
| `architecture-baseline/06-source-ingestion.md:57` — 4. Acquisition | `06-source-ingestion.md` | `ARCH-06-004`, `ARCH-06-005`, `ARCH-06-006`, `ARCH-06-007`, `ARCH-06-008` |
| `architecture-baseline/06-source-ingestion.md:74` — 4.1 Parser process/network/resource isolation | `06-source-ingestion.md` | `ARCH-06-009`, `ARCH-06-010` |
| `architecture-baseline/06-source-ingestion.md:80` — 5. Parsing requirements | `06-source-ingestion.md` | `ARCH-06-011` |
| `architecture-baseline/06-source-ingestion.md:91` — 6. Enrichment | `06-source-ingestion.md` | `ARCH-06-012` |
| `architecture-baseline/06-source-ingestion.md:107` — 7. Idempotency and versioning | `06-source-ingestion.md` | `ARCH-06-013` |
| `architecture-baseline/06-source-ingestion.md:111` — 8. Failure handling | `06-source-ingestion.md` | `ARCH-06-014`, `ARCH-06-015`, `ARCH-06-016`, `ARCH-06-017`, `ARCH-06-018`, `ARCH-06-019`, `ARCH-06-020` |
| `architecture-baseline/07-canonical-document-provenance.md:1` — 07 — Canonical Document Model and Provenance | `07-canonical-document-provenance.md` | Context only |
| `architecture-baseline/07-canonical-document-provenance.md:3` — 1. Why the canonical representation is foundational | `07-canonical-document-provenance.md` | `ARCH-07-001`, `ARCH-07-002` |
| `architecture-baseline/07-canonical-document-provenance.md:7` — 2. CanonicalDocument | `07-canonical-document-provenance.md` | Context only |
| `architecture-baseline/07-canonical-document-provenance.md:25` — 3. CanonicalNode | `07-canonical-document-provenance.md` | Context only |
| `architecture-baseline/07-canonical-document-provenance.md:44` — 4. Source locators | `07-canonical-document-provenance.md` | Context only |
| `architecture-baseline/07-canonical-document-provenance.md:48` — PDF | `07-canonical-document-provenance.md` | Context only |
| `architecture-baseline/07-canonical-document-provenance.md:55` — Audio/video | `07-canonical-document-provenance.md` | Context only |
| `architecture-baseline/07-canonical-document-provenance.md:62` — Image/figure | `07-canonical-document-provenance.md` | Context only |
| `architecture-baseline/07-canonical-document-provenance.md:70` — Spreadsheet | `07-canonical-document-provenance.md` | Context only |
| `architecture-baseline/07-canonical-document-provenance.md:76` — Web | `07-canonical-document-provenance.md` | Context only |
| `architecture-baseline/07-canonical-document-provenance.md:84` — 4.1 Note locators | `07-canonical-document-provenance.md` | `ARCH-07-003`, `ARCH-07-004` |
| `architecture-baseline/07-canonical-document-provenance.md:88` — Run/external evidence | `07-canonical-document-provenance.md` | Context only |
| `architecture-baseline/07-canonical-document-provenance.md:98` — 5. Provenance graph | `07-canonical-document-provenance.md` | Context only |
| `architecture-baseline/07-canonical-document-provenance.md:113` — 6. Derived versus authoritative content | `07-canonical-document-provenance.md` | `ARCH-07-005` |
| `architecture-baseline/07-canonical-document-provenance.md:127` — 7. Stable identifiers | `07-canonical-document-provenance.md` | `ARCH-07-006`, `ARCH-07-007` |
| `architecture-baseline/07-canonical-document-provenance.md:131` — 8. Citation design principle | `07-canonical-document-provenance.md` | `ARCH-07-008` |
| `architecture-baseline/08-knowledge-indexing.md:1` — 08 — Knowledge Storage and Indexing | `08-knowledge-indexing.md` | Context only |
| `architecture-baseline/08-knowledge-indexing.md:3` — 1. Principle | `08-knowledge-indexing.md` | Context only |
| `architecture-baseline/08-knowledge-indexing.md:7` — 2. Representations | `08-knowledge-indexing.md` | Context only |
| `architecture-baseline/08-knowledge-indexing.md:21` — 3. Chunking | `08-knowledge-indexing.md` | `ARCH-08-001`, `ARCH-08-002` |
| `architecture-baseline/08-knowledge-indexing.md:34` — 4. Lexical retrieval | `08-knowledge-indexing.md` | `ARCH-08-003` |
| `architecture-baseline/08-knowledge-indexing.md:38` — 5. Semantic retrieval | `08-knowledge-indexing.md` | `ARCH-08-004` |
| `architecture-baseline/08-knowledge-indexing.md:42` — 5.1 Multimodal evidence | `08-knowledge-indexing.md` | `ARCH-08-005`, `ARCH-08-006` |
| `architecture-baseline/08-knowledge-indexing.md:46` — 6. Metadata filters | `08-knowledge-indexing.md` | `ARCH-08-007` |
| `architecture-baseline/08-knowledge-indexing.md:50` — 7. Structural retrieval | `08-knowledge-indexing.md` | `ARCH-08-008` |
| `architecture-baseline/08-knowledge-indexing.md:54` — 8. Initial storage direction | `08-knowledge-indexing.md` | `ARCH-08-009` |
| `architecture-baseline/08-knowledge-indexing.md:58` — 9. Index lifecycle | `08-knowledge-indexing.md` | `ARCH-08-010` |
| `architecture-baseline/08-knowledge-indexing.md:63` — 10. Note-context indexing semantics | `08-knowledge-indexing.md` | `ARCH-08-011` |
| `architecture-baseline/09-retrieval-grounding.md:1` — 09 — Retrieval, Grounding and Citations | `09-retrieval-grounding.md` | Context only |
| `architecture-baseline/09-retrieval-grounding.md:3` — 1. Purpose | `09-retrieval-grounding.md` | Context only |
| `architecture-baseline/09-retrieval-grounding.md:7` — 2. Query pipeline | `09-retrieval-grounding.md` | Context only |
| `architecture-baseline/09-retrieval-grounding.md:26` — 3. Query understanding | `09-retrieval-grounding.md` | `ARCH-09-001` |
| `architecture-baseline/09-retrieval-grounding.md:30` — 4. Fusion and reranking | `09-retrieval-grounding.md` | `ARCH-09-002`, `ARCH-09-003`, `ARCH-09-004`, `ARCH-09-005` |
| `architecture-baseline/09-retrieval-grounding.md:34` — 5. Context assembly | `09-retrieval-grounding.md` | Context only |
| `architecture-baseline/09-retrieval-grounding.md:44` — 6. Grounded answer contract | `09-retrieval-grounding.md` | `ARCH-09-006` |
| `architecture-baseline/09-retrieval-grounding.md:55` — 7. Source-only behavior | `09-retrieval-grounding.md` | `ARCH-09-007`, `ARCH-09-008`, `ARCH-09-009`, `ARCH-09-010`, `ARCH-09-011`, `ARCH-09-012` |
| `architecture-baseline/09-retrieval-grounding.md:59` — 8. Citation validation | `09-retrieval-grounding.md` | `ARCH-09-013`, `ARCH-09-014`, `ARCH-09-015` |
| `architecture-baseline/09-retrieval-grounding.md:73` — 9. Contradictions | `09-retrieval-grounding.md` | `ARCH-09-016` |
| `architecture-baseline/09-retrieval-grounding.md:77` — 10. Evaluation | `09-retrieval-grounding.md` | `ARCH-09-017` |
| `architecture-baseline/10-model-provider-platform.md:1` — 10 — Model Provider Platform | `10-model-provider-platform.md` | Context only |
| `architecture-baseline/10-model-provider-platform.md:3` — 1. Goal | `10-model-provider-platform.md` | Context only |
| `architecture-baseline/10-model-provider-platform.md:7` — 2. Internal model concepts | `10-model-provider-platform.md` | Context only |
| `architecture-baseline/10-model-provider-platform.md:9` — Provider | `10-model-provider-platform.md` | Context only |
| `architecture-baseline/10-model-provider-platform.md:12` — Model | `10-model-provider-platform.md` | Context only |
| `architecture-baseline/10-model-provider-platform.md:15` — Capability descriptor | `10-model-provider-platform.md` | Context only |
| `architecture-baseline/10-model-provider-platform.md:18` — Model role | `10-model-provider-platform.md` | `ARCH-10-001` |
| `architecture-baseline/10-model-provider-platform.md:21` — 3. Capability descriptor | `10-model-provider-platform.md` | `ARCH-10-002`, `ARCH-10-003`, `ARCH-10-004` |
| `architecture-baseline/10-model-provider-platform.md:58` — 4. Internal request protocol | `10-model-provider-platform.md` | `ARCH-10-005`, `ARCH-10-006`, `ARCH-10-007` |
| `architecture-baseline/10-model-provider-platform.md:75` — 4.1 Realtime/duplex capability | `10-model-provider-platform.md` | `ARCH-10-008`, `ARCH-10-009` |
| `architecture-baseline/10-model-provider-platform.md:79` — 4.2 Remote asynchronous media operations | `10-model-provider-platform.md` | `ARCH-10-010`, `ARCH-10-011` |
| `architecture-baseline/10-model-provider-platform.md:85` — 5. Provider adapters | `10-model-provider-platform.md` | Context only |
| `architecture-baseline/10-model-provider-platform.md:95` — 6. Big Pickle baseline | `10-model-provider-platform.md` | `ARCH-10-012`, `ARCH-10-013`, `ARCH-10-014`, `ARCH-10-015`, `ARCH-10-016` |
| `architecture-baseline/10-model-provider-platform.md:103` — 7. Routing | `10-model-provider-platform.md` | `ARCH-10-017`, `ARCH-10-018` |
| `architecture-baseline/10-model-provider-platform.md:117` — 8. Local inference | `10-model-provider-platform.md` | `ARCH-10-019` |
| `architecture-baseline/10-model-provider-platform.md:121` — 9. Failure, cancellation and fallback | `10-model-provider-platform.md` | `ARCH-10-020`, `ARCH-10-021`, `ARCH-10-022`, `ARCH-10-023`, `ARCH-10-024` |
| `architecture-baseline/10-model-provider-platform.md:127` — 10. Cost and quota controls | `10-model-provider-platform.md` | `ARCH-10-025`, `ARCH-10-026` |
| `architecture-baseline/10-model-provider-platform.md:131` — 11. Provider credentials | `10-model-provider-platform.md` | `ARCH-10-027`, `ARCH-10-028`, `ARCH-10-029` |
| `architecture-baseline/11-agent-research-runtime.md:1` — 11 — Agent and Research Runtime | `11-agent-research-runtime.md` | Context only |
| `architecture-baseline/11-agent-research-runtime.md:3` — 1. Purpose | `11-agent-research-runtime.md` | Context only |
| `architecture-baseline/11-agent-research-runtime.md:7` — 2. Research lifecycle | `11-agent-research-runtime.md` | Context only |
| `architecture-baseline/11-agent-research-runtime.md:23` — 3. Agent state | `11-agent-research-runtime.md` | `ARCH-11-001` |
| `architecture-baseline/11-agent-research-runtime.md:45` — 4. Tool registry | `11-agent-research-runtime.md` | Context only |
| `architecture-baseline/11-agent-research-runtime.md:64` — 5. Research source quality | `11-agent-research-runtime.md` | `ARCH-11-002` |
| `architecture-baseline/11-agent-research-runtime.md:68` — 6. User control | `11-agent-research-runtime.md` | `ARCH-11-003`, `ARCH-11-004` |
| `architecture-baseline/11-agent-research-runtime.md:72` — 7. Fast research versus Deep Research | `11-agent-research-runtime.md` | Context only |
| `architecture-baseline/11-agent-research-runtime.md:81` — 8. Browser automation | `11-agent-research-runtime.md` | `ARCH-11-005`, `ARCH-11-006`, `ARCH-11-007`, `ARCH-11-008`, `ARCH-11-009` |
| `architecture-baseline/11-agent-research-runtime.md:85` — 9. Relationship to chat | `11-agent-research-runtime.md` | `ARCH-11-010`, `ARCH-11-011`, `ARCH-11-012` |
| `architecture-baseline/12-bubblewrap-execution.md:1` — 12 — Local Isolated Code Execution with Bubblewrap | `12-bubblewrap-execution.md` | Context only |
| `architecture-baseline/12-bubblewrap-execution.md:3` — 1. Rationale | `12-bubblewrap-execution.md` | `ARCH-12-001` |
| `architecture-baseline/12-bubblewrap-execution.md:9` — 2. Abstraction | `12-bubblewrap-execution.md` | Context only |
| `architecture-baseline/12-bubblewrap-execution.md:26` — 3. Linux identities | `12-bubblewrap-execution.md` | Context only |
| `architecture-baseline/12-bubblewrap-execution.md:36` — 4. Isolation profile | `12-bubblewrap-execution.md` | `ARCH-12-002`, `ARCH-12-003`, `ARCH-12-004` |
| `architecture-baseline/12-bubblewrap-execution.md:57` — 5. Resource controls | `12-bubblewrap-execution.md` | `ARCH-12-005`, `ARCH-12-006`, `ARCH-12-007` |
| `architecture-baseline/12-bubblewrap-execution.md:71` — 6. Runtime image | `12-bubblewrap-execution.md` | `ARCH-12-008` |
| `architecture-baseline/12-bubblewrap-execution.md:85` — 7. Input/output contract | `12-bubblewrap-execution.md` | `ARCH-12-009`, `ARCH-12-010` |
| `architecture-baseline/12-bubblewrap-execution.md:89` — 8. Networking | `12-bubblewrap-execution.md` | `ARCH-12-011`, `ARCH-12-012`, `ARCH-12-013` |
| `architecture-baseline/12-bubblewrap-execution.md:95` — 9. Auditability | `12-bubblewrap-execution.md` | `ARCH-12-014` |
| `architecture-baseline/12-bubblewrap-execution.md:99` — 10. Threat model | `12-bubblewrap-execution.md` | `ARCH-12-015` |
| `architecture-baseline/12-bubblewrap-execution.md:103` — 11. Version and host prerequisites | `12-bubblewrap-execution.md` | `ARCH-12-016`, `ARCH-12-017`, `ARCH-12-018` |
| `architecture-baseline/12-bubblewrap-execution.md:107` — 12. Upstream security references | `12-bubblewrap-execution.md` | Context only |
| `architecture-baseline/13-studio-artifacts.md:1` — 13 — Studio and Artifact Framework | `13-studio-artifacts.md` | Context only |
| `architecture-baseline/13-studio-artifacts.md:3` — 1. Principle | `13-studio-artifacts.md` | Context only |
| `architecture-baseline/13-studio-artifacts.md:7` — 2. Generic lifecycle | `13-studio-artifacts.md` | Context only |
| `architecture-baseline/13-studio-artifacts.md:20` — 3. Artifact data model | `13-studio-artifacts.md` | Context only |
| `architecture-baseline/13-studio-artifacts.md:36` — 4. Initial artifact types | `13-studio-artifacts.md` | Context only |
| `architecture-baseline/13-studio-artifacts.md:38` — Reports | `13-studio-artifacts.md` | `ARCH-13-001`, `ARCH-13-002`, `ARCH-13-003`, `ARCH-13-004` |
| `architecture-baseline/13-studio-artifacts.md:46` — Data tables | `13-studio-artifacts.md` | `ARCH-13-005` |
| `architecture-baseline/13-studio-artifacts.md:49` — Mind maps | `13-studio-artifacts.md` | `ARCH-13-006` |
| `architecture-baseline/13-studio-artifacts.md:52` — Flashcards | `13-studio-artifacts.md` | Context only |
| `architecture-baseline/13-studio-artifacts.md:55` — Quizzes | `13-studio-artifacts.md` | `ARCH-13-007` |
| `architecture-baseline/13-studio-artifacts.md:58` — Slide decks | `13-studio-artifacts.md` | `ARCH-13-008` |
| `architecture-baseline/13-studio-artifacts.md:61` — Infographics | `13-studio-artifacts.md` | Context only |
| `architecture-baseline/13-studio-artifacts.md:64` — Audio Overview | `13-studio-artifacts.md` | Context only |
| `architecture-baseline/13-studio-artifacts.md:67` — Video Overview | `13-studio-artifacts.md` | Context only |
| `architecture-baseline/13-studio-artifacts.md:70` — 5. Recipe system | `13-studio-artifacts.md` | Context only |
| `architecture-baseline/13-studio-artifacts.md:74` — 6. Revision | `13-studio-artifacts.md` | `ARCH-13-009`, `ARCH-13-010`, `ARCH-13-011`, `ARCH-13-012` |
| `architecture-baseline/13-studio-artifacts.md:88` — 7. Extension boundary | `13-studio-artifacts.md` | `ARCH-13-013`, `ARCH-13-014` |
| `architecture-baseline/14-media-realtime.md:1` — 14 — Media, Audio, Video and Realtime Interaction | `14-media-realtime.md` | Context only |
| `architecture-baseline/14-media-realtime.md:3` — 1. Media capability layer | `14-media-realtime.md` | `ARCH-14-001` |
| `architecture-baseline/14-media-realtime.md:16` — 2. Audio Overview pipeline | `14-media-realtime.md` | `ARCH-14-002` |
| `architecture-baseline/14-media-realtime.md:31` — 3. Audio modes | `14-media-realtime.md` | Context only |
| `architecture-baseline/14-media-realtime.md:35` — 4. Realtime interactive audio | `14-media-realtime.md` | `ARCH-14-003`, `ARCH-14-004`, `ARCH-14-005` |
| `architecture-baseline/14-media-realtime.md:52` — 4.1 Recorded-audio source capture | `14-media-realtime.md` | `ARCH-14-006` |
| `architecture-baseline/14-media-realtime.md:57` — 5. Video Overview pipeline | `14-media-realtime.md` | Context only |
| `architecture-baseline/14-media-realtime.md:71` — 6. Video modes and Cinematic mode | `14-media-realtime.md` | `ARCH-14-007`, `ARCH-14-008` |
| `architecture-baseline/14-media-realtime.md:75` — 7. Media provenance | `14-media-realtime.md` | `ARCH-14-009` |
| `architecture-baseline/14-media-realtime.md:79` — 7.1 Provider-supplied media provenance | `14-media-realtime.md` | `ARCH-14-010` |
| `architecture-baseline/14-media-realtime.md:83` — 7.2 Generated-media validation and renditions | `14-media-realtime.md` | `ARCH-14-011` |
| `architecture-baseline/14-media-realtime.md:89` — 7.3 Safety, refusals and rights metadata | `14-media-realtime.md` | `ARCH-14-012`, `ARCH-14-013` |
| `architecture-baseline/14-media-realtime.md:93` — 8. Storage and lifecycle | `14-media-realtime.md` | `ARCH-14-014`, `ARCH-14-015`, `ARCH-14-016` |
| `architecture-baseline/15-jobs-events.md:1` — 15 — Jobs and Orchestration | `15-jobs-events.md` | Context only |
| `architecture-baseline/15-jobs-events.md:3` — 1. Why jobs are core | `15-jobs-events.md` | Context only |
| `architecture-baseline/15-jobs-events.md:7` — 2. Job state model | `15-jobs-events.md` | `ARCH-15-001` |
| `architecture-baseline/15-jobs-events.md:23` — 3. Job classes | `15-jobs-events.md` | Context only |
| `architecture-baseline/15-jobs-events.md:35` — 4. Idempotency | `15-jobs-events.md` | `ARCH-15-002`, `ARCH-15-003`, `ARCH-15-004`, `ARCH-15-005`, `ARCH-15-006`, `ARCH-15-007` |
| `architecture-baseline/15-jobs-events.md:41` — 4.1 Client-command idempotency | `15-jobs-events.md` | `ARCH-15-008` |
| `architecture-baseline/15-jobs-events.md:45` — 4.2 Remote provider jobs and staged media recovery | `15-jobs-events.md` | `ARCH-15-009`, `ARCH-15-010` |
| `architecture-baseline/15-jobs-events.md:51` — 5. Events | `15-jobs-events.md` | Context only |
| `architecture-baseline/15-jobs-events.md:70` — 6. Delivery semantics | `15-jobs-events.md` | `ARCH-15-011`, `ARCH-15-012`, `ARCH-15-013` |
| `architecture-baseline/15-jobs-events.md:74` — 6.1 Worker leases and orphan recovery | `15-jobs-events.md` | `ARCH-15-014` |
| `architecture-baseline/15-jobs-events.md:78` — 6.2 Durable message/event metadata | `15-jobs-events.md` | `ARCH-15-015`, `ARCH-15-016` |
| `architecture-baseline/15-jobs-events.md:82` — 7. Cancellation and authorization changes | `15-jobs-events.md` | `ARCH-15-017`, `ARCH-15-018`, `ARCH-15-019`, `ARCH-15-020` |
| `architecture-baseline/15-jobs-events.md:88` — 8. Priority and fairness | `15-jobs-events.md` | `ARCH-15-021` |
| `architecture-baseline/15-jobs-events.md:92` — 8.1 Capacity-aware deferred generation | `15-jobs-events.md` | `ARCH-15-022` |
| `architecture-baseline/15-jobs-events.md:96` — 8.2 User-facing completion notifications | `15-jobs-events.md` | `ARCH-15-023`, `ARCH-15-024`, `ARCH-15-025` |
| `architecture-baseline/15-jobs-events.md:100` — 9. External-provider disclosure events | `15-jobs-events.md` | `ARCH-15-026` |
| `architecture-baseline/15-jobs-events.md:104` — 10. Frontend updates | `15-jobs-events.md` | `ARCH-15-027` |
| `architecture-baseline/16-api-frontend.md:1` — 16 — API and Frontend Architecture | `16-api-frontend.md` | Context only |
| `architecture-baseline/16-api-frontend.md:3` — 1. Primary UX model | `16-api-frontend.md` | `ARCH-16-001` |
| `architecture-baseline/16-api-frontend.md:15` — 2. Frontend capabilities | `16-api-frontend.md` | `ARCH-16-002`, `ARCH-16-003` |
| `architecture-baseline/16-api-frontend.md:47` — 3. API style | `16-api-frontend.md` | `ARCH-16-004` |
| `architecture-baseline/16-api-frontend.md:58` — 4. Resource-oriented API | `16-api-frontend.md` | Context only |
| `architecture-baseline/16-api-frontend.md:76` — 4.1 External automation API (deferred) | `16-api-frontend.md` | `ARCH-16-005` |
| `architecture-baseline/16-api-frontend.md:80` — 5. Streaming | `16-api-frontend.md` | `ARCH-16-006`, `ARCH-16-007` |
| `architecture-baseline/16-api-frontend.md:92` — 5.1 Stream disconnect and reconnect semantics | `16-api-frontend.md` | `ARCH-16-008` |
| `architecture-baseline/16-api-frontend.md:98` — 6. Source viewer | `16-api-frontend.md` | `ARCH-16-009` |
| `architecture-baseline/16-api-frontend.md:102` — 7. Responsive asynchronous web application | `16-api-frontend.md` | `ARCH-16-010`, `ARCH-16-011` |
| `architecture-baseline/17-auth-sharing.md:1` — 17 — Authentication, Authorization, Sharing and Collaboration | `17-auth-sharing.md` | Context only |
| `architecture-baseline/17-auth-sharing.md:3` — 1. Multi-user requirement | `17-auth-sharing.md` | `ARCH-17-001` |
| `architecture-baseline/17-auth-sharing.md:7` — 2. Initial roles and permission baseline | `17-auth-sharing.md` | `ARCH-17-002` |
| `architecture-baseline/17-auth-sharing.md:18` — 2.1 Permission matrix | `17-auth-sharing.md` | `ARCH-17-003` |
| `architecture-baseline/17-auth-sharing.md:41` — 3. Notebook sharing | `17-auth-sharing.md` | `ARCH-17-004`, `ARCH-17-005` |
| `architecture-baseline/17-auth-sharing.md:55` — 3.1 Notebook copy semantics | `17-auth-sharing.md` | `ARCH-17-006`, `ARCH-17-007` |
| `architecture-baseline/17-auth-sharing.md:59` — 4. Public and featured notebooks | `17-auth-sharing.md` | `ARCH-17-008`, `ARCH-17-009`, `ARCH-17-010`, `ARCH-17-011`, `ARCH-17-012`, `ARCH-17-013`, `ARCH-17-014` |
| `architecture-baseline/17-auth-sharing.md:69` — 5. Authorization checks | `17-auth-sharing.md` | `ARCH-17-015`, `ARCH-17-016` |
| `architecture-baseline/17-auth-sharing.md:84` — 6. Connector-supplied source restrictions | `17-auth-sharing.md` | `ARCH-17-017`, `ARCH-17-018`, `ARCH-17-019` |
| `architecture-baseline/17-auth-sharing.md:88` — 7. Authentication mechanism | `17-auth-sharing.md` | `ARCH-17-020`, `ARCH-17-021` |
| `architecture-baseline/17-auth-sharing.md:92` — 7.1 Initial administrator bootstrap and recovery | `17-auth-sharing.md` | `ARCH-17-022`, `ARCH-17-023`, `ARCH-17-024` |
| `architecture-baseline/17-auth-sharing.md:96` — 7.2 Trusted reverse-proxy authentication boundary | `17-auth-sharing.md` | `ARCH-17-025`, `ARCH-17-026`, `ARCH-17-027`, `ARCH-17-028` |
| `architecture-baseline/17-auth-sharing.md:100` — 8. Provider credential ownership | `17-auth-sharing.md` | `ARCH-17-029` |
| `architecture-baseline/17-auth-sharing.md:104` — 9. User/account lifecycle | `17-auth-sharing.md` | `ARCH-17-030`, `ARCH-17-031` |
| `architecture-baseline/17-auth-sharing.md:110` — 10. Authorization changes during jobs | `17-auth-sharing.md` | `ARCH-17-032` |
| `architecture-baseline/17-auth-sharing.md:114` — 11. Collaboration | `17-auth-sharing.md` | `ARCH-17-033` |
| `architecture-baseline/18-observability-evaluation.md:1` — 18 — Observability and Evaluation | `18-observability-evaluation.md` | Context only |
| `architecture-baseline/18-observability-evaluation.md:3` — 1. Principle | `18-observability-evaluation.md` | Context only |
| `architecture-baseline/18-observability-evaluation.md:7` — 2. Request tracing | `18-observability-evaluation.md` | `ARCH-18-001` |
| `architecture-baseline/18-observability-evaluation.md:29` — 3. Metrics | `18-observability-evaluation.md` | Context only |
| `architecture-baseline/18-observability-evaluation.md:31` — System | `18-observability-evaluation.md` | Context only |
| `architecture-baseline/18-observability-evaluation.md:39` — Models | `18-observability-evaluation.md` | Context only |
| `architecture-baseline/18-observability-evaluation.md:49` — Retrieval | `18-observability-evaluation.md` | Context only |
| `architecture-baseline/18-observability-evaluation.md:56` — 4. Evaluation corpus | `18-observability-evaluation.md` | Context only |
| `architecture-baseline/18-observability-evaluation.md:60` — 5. Retrieval metrics | `18-observability-evaluation.md` | Context only |
| `architecture-baseline/18-observability-evaluation.md:68` — 6. Grounding metrics | `18-observability-evaluation.md` | Context only |
| `architecture-baseline/18-observability-evaluation.md:82` — 7. Generation metrics | `18-observability-evaluation.md` | Context only |
| `architecture-baseline/18-observability-evaluation.md:93` — 7.1 Version-consistency evaluation | `18-observability-evaluation.md` | `ARCH-18-002` |
| `architecture-baseline/18-observability-evaluation.md:97` — 8. Provider/model comparison | `18-observability-evaluation.md` | `ARCH-18-003`, `ARCH-18-004` |
| `architecture-baseline/18-observability-evaluation.md:101` — 9. Privacy | `18-observability-evaluation.md` | `ARCH-18-005` |
| `architecture-baseline/18-observability-evaluation.md:105` — 10. Evaluation protocol and release oracle | `18-observability-evaluation.md` | `ARCH-18-006`, `ARCH-18-007`, `ARCH-18-008` |
| `architecture-baseline/19-security-privacy.md:1` — 19 — Security, Privacy and Data Governance | `19-security-privacy.md` | Context only |
| `architecture-baseline/19-security-privacy.md:3` — 1. Security model | `19-security-privacy.md` | Context only |
| `architecture-baseline/19-security-privacy.md:7` — 2. Data classes | `19-security-privacy.md` | Context only |
| `architecture-baseline/19-security-privacy.md:11` — 3. External provider policy | `19-security-privacy.md` | `ARCH-19-001`, `ARCH-19-002`, `ARCH-19-003`, `ARCH-19-004`, `ARCH-19-005`, `ARCH-19-006` |
| `architecture-baseline/19-security-privacy.md:28` — 4. Prompt injection | `19-security-privacy.md` | `ARCH-19-007`, `ARCH-19-008` |
| `architecture-baseline/19-security-privacy.md:32` — 5. Secrets | `19-security-privacy.md` | `ARCH-19-009`, `ARCH-19-010`, `ARCH-19-011`, `ARCH-19-012`, `ARCH-19-013`, `ARCH-19-014`, `ARCH-19-015`, `ARCH-19-016` |
| `architecture-baseline/19-security-privacy.md:44` — 6. Isolation | `19-security-privacy.md` | `ARCH-19-017`, `ARCH-19-018`, `ARCH-19-019` |
| `architecture-baseline/19-security-privacy.md:50` — 7. Upload safety | `19-security-privacy.md` | `ARCH-19-020`, `ARCH-19-021`, `ARCH-19-022` |
| `architecture-baseline/19-security-privacy.md:56` — 7.1 External references inside documents | `19-security-privacy.md` | `ARCH-19-023`, `ARCH-19-024` |
| `architecture-baseline/19-security-privacy.md:60` — 8. Web acquisition and SSRF safety | `19-security-privacy.md` | `ARCH-19-025`, `ARCH-19-026`, `ARCH-19-027`, `ARCH-19-028`, `ARCH-19-029` |
| `architecture-baseline/19-security-privacy.md:64` — 8.1 Provider endpoint and callback safety | `19-security-privacy.md` | `ARCH-19-030`, `ARCH-19-031` |
| `architecture-baseline/19-security-privacy.md:70` — 9. Authorization boundary | `19-security-privacy.md` | `ARCH-19-032` |
| `architecture-baseline/19-security-privacy.md:74` — 9.0 Historical-reference authorization | `19-security-privacy.md` | `ARCH-19-033`, `ARCH-19-034` |
| `architecture-baseline/19-security-privacy.md:78` — 9.1 Browser/UI content isolation | `19-security-privacy.md` | `ARCH-19-035`, `ARCH-19-036` |
| `architecture-baseline/19-security-privacy.md:82` — 9.2 Cache isolation | `19-security-privacy.md` | `ARCH-19-037`, `ARCH-19-038`, `ARCH-19-039` |
| `architecture-baseline/19-security-privacy.md:86` — 10. Audit log | `19-security-privacy.md` | `ARCH-19-040` |
| `architecture-baseline/19-security-privacy.md:100` — 11. Source access and export restrictions | `19-security-privacy.md` | `ARCH-19-041`, `ARCH-19-042` |
| `architecture-baseline/19-security-privacy.md:104` — 12. Deletion, purge and backups | `19-security-privacy.md` | `ARCH-19-043`, `ARCH-19-044`, `ARCH-19-045`, `ARCH-19-046`, `ARCH-19-047` |
| `architecture-baseline/19-security-privacy.md:116` — 12.1 Blob integrity and garbage collection | `19-security-privacy.md` | `ARCH-19-048`, `ARCH-19-049`, `ARCH-19-050`, `ARCH-19-051` |
| `architecture-baseline/20-extension-boundaries.md:1` — 20 — Internal Extension Boundaries | `20-extension-boundaries.md` | Context only |
| `architecture-baseline/20-extension-boundaries.md:3` — 1. Goal | `20-extension-boundaries.md` | Context only |
| `architecture-baseline/20-extension-boundaries.md:7` — 2. Internal extension boundaries | `20-extension-boundaries.md` | `ARCH-20-001` |
| `architecture-baseline/20-extension-boundaries.md:19` — 3. Versioning | `20-extension-boundaries.md` | `ARCH-20-002` |
| `architecture-baseline/20-extension-boundaries.md:23` — 4. Explicitly deferred ecosystem work | `20-extension-boundaries.md` | `ARCH-20-003`, `ARCH-20-004` |
| `architecture-baseline/21-nonfunctional-requirements.md:1` — 21 — Non-Functional Requirements | `21-nonfunctional-requirements.md` | Context only |
| `architecture-baseline/21-nonfunctional-requirements.md:3` — 0. Reference acceptance profile | `21-nonfunctional-requirements.md` | `ARCH-21-001` |
| `architecture-baseline/21-nonfunctional-requirements.md:16` — 1. Reliability | `21-nonfunctional-requirements.md` | `ARCH-21-002`, `ARCH-21-003`, `ARCH-21-004`, `ARCH-21-005`, `ARCH-21-006` |
| `architecture-baseline/21-nonfunctional-requirements.md:24` — 1.1 Data integrity and concurrency | `21-nonfunctional-requirements.md` | `ARCH-21-007`, `ARCH-21-008`, `ARCH-21-009`, `ARCH-21-010`, `ARCH-21-011` |
| `architecture-baseline/21-nonfunctional-requirements.md:28` — 2. Performance | `21-nonfunctional-requirements.md` | `ARCH-21-012`, `ARCH-21-013`, `ARCH-21-014`, `ARCH-21-015`, `ARCH-21-016`, `ARCH-21-017`, `ARCH-21-018` |
| `architecture-baseline/21-nonfunctional-requirements.md:39` — 3. Scalability | `21-nonfunctional-requirements.md` | `ARCH-21-019`, `ARCH-21-020` |
| `architecture-baseline/21-nonfunctional-requirements.md:43` — 4. Portability | `21-nonfunctional-requirements.md` | `ARCH-21-021` |
| `architecture-baseline/21-nonfunctional-requirements.md:47` — 5. Maintainability | `21-nonfunctional-requirements.md` | `ARCH-21-022`, `ARCH-21-023` |
| `architecture-baseline/21-nonfunctional-requirements.md:51` — 6. Reproducibility | `21-nonfunctional-requirements.md` | `ARCH-21-024` |
| `architecture-baseline/21-nonfunctional-requirements.md:57` — 7. Accessibility | `21-nonfunctional-requirements.md` | `ARCH-21-025`, `ARCH-21-026`, `ARCH-21-027`, `ARCH-21-028` |
| `architecture-baseline/21-nonfunctional-requirements.md:61` — 7.1 Data portability | `21-nonfunctional-requirements.md` | Context only |
| `architecture-baseline/21-nonfunctional-requirements.md:65` — 8. Internationalization | `21-nonfunctional-requirements.md` | `ARCH-21-029`, `ARCH-21-030`, `ARCH-21-031` |
| `architecture-baseline/21-nonfunctional-requirements.md:69` — 9. Backup/restore | `21-nonfunctional-requirements.md` | `ARCH-21-032`, `ARCH-21-033`, `ARCH-21-034`, `ARCH-21-035`, `ARCH-21-036` |
| `architecture-baseline/21-nonfunctional-requirements.md:75` — 10. Upgradeability | `21-nonfunctional-requirements.md` | `ARCH-21-037` |
| `architecture-baseline/21-nonfunctional-requirements.md:79` — 11. Testability | `21-nonfunctional-requirements.md` | `ARCH-21-038`, `ARCH-21-039` |
| `architecture-baseline/21-nonfunctional-requirements.md:83` — 12. Dependency and supply-chain hygiene | `21-nonfunctional-requirements.md` | `ARCH-21-040`, `ARCH-21-041` |
| `architecture-baseline/21-nonfunctional-requirements.md:87` — 13. Operability and degraded mode | `21-nonfunctional-requirements.md` | `ARCH-21-042`, `ARCH-21-043`, `ARCH-21-044`, `ARCH-21-045` |
| `architecture-baseline/22-dependencies-phases.md:1` — 22 — Dependency Graph and Implementation Phases | `22-dependencies-phases.md` | Context only |
| `architecture-baseline/22-dependencies-phases.md:3` — 1. Architectural dependency hierarchy | `22-dependencies-phases.md` | Context only |
| `architecture-baseline/22-dependencies-phases.md:21` — 1.1 Reference-deployment dependency inventory | `22-dependencies-phases.md` | `ARCH-22-001`, `ARCH-22-002` |
| `architecture-baseline/22-dependencies-phases.md:47` — 2. Phase 0 — Skeleton and architecture harness | `22-dependencies-phases.md` | Context only |
| `architecture-baseline/22-dependencies-phases.md:65` — 3. Phase 1 — Source-to-grounded-chat vertical slice | `22-dependencies-phases.md` | Context only |
| `architecture-baseline/22-dependencies-phases.md:81` — 4. Phase 2 — Universal ingestion and robust retrieval | `22-dependencies-phases.md` | Context only |
| `architecture-baseline/22-dependencies-phases.md:85` — 5. Phase 3 — Research and execution | `22-dependencies-phases.md` | Context only |
| `architecture-baseline/22-dependencies-phases.md:89` — 6. Phase 4 — Text/data Studio | `22-dependencies-phases.md` | Context only |
| `architecture-baseline/22-dependencies-phases.md:93` — 7. Phase 5 — Visual/document Studio | `22-dependencies-phases.md` | Context only |
| `architecture-baseline/22-dependencies-phases.md:97` — 8. Phase 6 — Audio/video | `22-dependencies-phases.md` | Context only |
| `architecture-baseline/22-dependencies-phases.md:101` — 9. Phase 7 — Collaboration and late parity | `22-dependencies-phases.md` | `ARCH-22-003` |
| `architecture-baseline/22-dependencies-phases.md:106` — 10. Parity-to-phase coverage | `22-dependencies-phases.md` | `ARCH-22-004`, `ARCH-22-005` |
| `architecture-baseline/22-dependencies-phases.md:122` — 11. Cross-phase rules | `22-dependencies-phases.md` | `ARCH-22-006` |
| `architecture-baseline/23-open-questions-adrs.md:1` — 23 — Architecture Decisions and Implementation Choices | `23-open-questions-adrs.md` | Context only |
| `architecture-baseline/23-open-questions-adrs.md:5` — 1. Resolved questions from the planning review | `23-open-questions-adrs.md` | Context only |
| `architecture-baseline/23-open-questions-adrs.md:7` — Q-001 — External-provider default policy and disclosure | `23-open-questions-adrs.md` | Context only |
| `architecture-baseline/23-open-questions-adrs.md:11` — Q-002 — Network access inside Bubblewrap executions | `23-open-questions-adrs.md` | Context only |
| `architecture-baseline/23-open-questions-adrs.md:15` — Q-003 — Remote-source refresh semantics | `23-open-questions-adrs.md` | Context only |
| `architecture-baseline/23-open-questions-adrs.md:19` — Q-004 — Authentication integration | `23-open-questions-adrs.md` | Context only |
| `architecture-baseline/23-open-questions-adrs.md:23` — Q-005 — Initial persistence/orchestration stack | `23-open-questions-adrs.md` | Context only |
| `architecture-baseline/23-open-questions-adrs.md:27` — Q-006 — Initial embedding and reranker models | `23-open-questions-adrs.md` | `ARCH-23-001` |
| `architecture-baseline/23-open-questions-adrs.md:31` — Q-007 — Web research backend | `23-open-questions-adrs.md` | Context only |
| `architecture-baseline/23-open-questions-adrs.md:35` — Q-008 — Provider configuration UX | `23-open-questions-adrs.md` | Context only |
| `architecture-baseline/23-open-questions-adrs.md:39` — Q-009 — Frontend/backend implementation stack | `23-open-questions-adrs.md` | `ARCH-23-002` |
| `architecture-baseline/23-open-questions-adrs.md:43` — Q-010 — Source/notebook limits | `23-open-questions-adrs.md` | Context only |
| `architecture-baseline/23-open-questions-adrs.md:47` — Q-011 — Hard deletion versus historical reproducibility | `23-open-questions-adrs.md` | Context only |
| `architecture-baseline/23-open-questions-adrs.md:51` — 2. Resolved ADR index | `23-open-questions-adrs.md` | Context only |
| `architecture-baseline/23-open-questions-adrs.md:80` — 3. Implementation selections intentionally deferred | `23-open-questions-adrs.md` | `ARCH-23-003`, `ARCH-23-004` |
| `architecture-baseline/24-glossary.md:1` — 24 — Glossary | `24-glossary.md` | Context only |
| `architecture-baseline/25-software-testing-release-engineering.md:1` — 25 — Software Testing, Release Engineering and Supply Chain | `25-software-testing-release-engineering.md` | Context only |
| `architecture-baseline/25-software-testing-release-engineering.md:3` — 1. Purpose | `25-software-testing-release-engineering.md` | `ARCH-25-001` |
| `architecture-baseline/25-software-testing-release-engineering.md:7` — 2. Test layers | `25-software-testing-release-engineering.md` | `ARCH-25-002`, `ARCH-25-003`, `ARCH-25-004` |
| `architecture-baseline/25-software-testing-release-engineering.md:37` — 3. Parser and provenance golden corpus | `25-software-testing-release-engineering.md` | Context only |
| `architecture-baseline/25-software-testing-release-engineering.md:41` — 4. Authorization regression suite | `25-software-testing-release-engineering.md` | `ARCH-25-005`, `ARCH-25-006`, `ARCH-25-007`, `ARCH-25-008`, `ARCH-25-009` |
| `architecture-baseline/25-software-testing-release-engineering.md:51` — 5. Provider compatibility suite | `25-software-testing-release-engineering.md` | `ARCH-25-010` |
| `architecture-baseline/25-software-testing-release-engineering.md:55` — 6. Reproducible builds and dependencies | `25-software-testing-release-engineering.md` | `ARCH-25-011`, `ARCH-25-012`, `ARCH-25-013` |
| `architecture-baseline/25-software-testing-release-engineering.md:59` — 7. Security update policy | `25-software-testing-release-engineering.md` | `ARCH-25-014` |
| `architecture-baseline/25-software-testing-release-engineering.md:63` — 8. Release gates | `25-software-testing-release-engineering.md` | `ARCH-25-015`, `ARCH-25-016` |
| `architecture-baseline/25-software-testing-release-engineering.md:79` — 9. Versioning | `25-software-testing-release-engineering.md` | `ARCH-25-017` |
| `architecture-baseline/25-software-testing-release-engineering.md:84` — 10. Mutable-note and generation-input regression tests | `25-software-testing-release-engineering.md` | `ARCH-25-018`, `ARCH-25-019`, `ARCH-25-020`, `ARCH-25-021`, `ARCH-25-022`, `ARCH-25-023`, `ARCH-25-024` |
| `architecture-baseline/25-software-testing-release-engineering.md:88` — 11. Technical-specification traceability contract | `25-software-testing-release-engineering.md` | `ARCH-25-025`, `ARCH-25-026`, `ARCH-25-027`, `ARCH-25-028`, `ARCH-25-029`, `ARCH-25-030`, `ARCH-25-031`, `ARCH-25-032`, `ARCH-25-033`, `ARCH-25-034` |
| `architecture-baseline/25-software-testing-release-engineering.md:101` — 11.1 Capability/conformance profile and `N/A` rules | `25-software-testing-release-engineering.md` | `ARCH-25-035` |
| `architecture-baseline/25-software-testing-release-engineering.md:107` — 12. Required test-case form and oracle hierarchy | `25-software-testing-release-engineering.md` | `ARCH-25-036`, `ARCH-25-037`, `ARCH-25-038` |
| `architecture-baseline/25-software-testing-release-engineering.md:124` — 13. Deterministic reference test harness | `25-software-testing-release-engineering.md` | `ARCH-25-039`, `ARCH-25-040`, `ARCH-25-041` |
| `architecture-baseline/25-software-testing-release-engineering.md:142` — 14. Canonical automated end-to-end journeys | `25-software-testing-release-engineering.md` | `ARCH-25-042`, `ARCH-25-043`, `ARCH-25-044` |
| `architecture-baseline/25-software-testing-release-engineering.md:164` — 15. Manual end-to-end and exploratory runbook | `25-software-testing-release-engineering.md` | `ARCH-25-045`, `ARCH-25-046`, `ARCH-25-047` |
| `architecture-baseline/25-software-testing-release-engineering.md:187` — 16. Browser, CI and execution tiers | `25-software-testing-release-engineering.md` | `ARCH-25-048` |
| `architecture-baseline/25-software-testing-release-engineering.md:201` — 17. Meaningfulness, nondeterminism and flaky-test policy | `25-software-testing-release-engineering.md` | `ARCH-25-049` |
| `architecture-baseline/25-software-testing-release-engineering.md:209` — 18. Definition of done for technical-specification handoff | `25-software-testing-release-engineering.md` | `ARCH-25-050` |
