# 06 — Universal Source Ingestion

## 1. Responsibility

The ingestion subsystem converts heterogeneous external content into immutable source snapshots and canonical documents suitable for search, citation and artifact generation.

## 2. Input adapters

The architecture MUST allow adapters for:

### File sources
- PDF;
- DOCX;
- PPTX;
- TXT;
- Markdown;
- CSV;
- spreadsheet formats;
- EPUB;
- image formats;
- audio/speech-bearing media formats accepted by the STT pipeline (the reference product treats these as transcribed audio sources, even when a supported container such as MP4/AVI is used).

### Network sources
- webpage URL;
- YouTube/public video URL;
- downloadable documents reached through an explicit URL/import path.

### Connector sources
- optional cloud document/storage connectors;
- optional authenticated/restricted repository connectors;

Connector support is vendor-neutral. No Google account or Google service is required for baseline operation, and implementing a catalog of enterprise connectors is not a parity-baseline requirement.

A connector contract SHOULD expose acquisition plus, where supported, enumerate/search, stable upstream revision/version identifiers, refresh/sync, access-revocation detection, optional per-user source-access checks and source-derived sharing/export restrictions. Connector credentials are handled outside the canonical document model.

### Internal/generated sources
- pasted text;
- notebook notes promoted to sources;
- research results explicitly imported as sources.

## 3. Ingestion stages

```mermaid
flowchart LR
    A[Source request] --> B[Acquire]
    B --> C[Type detection]
    C --> D[Parse / decode]
    D --> E[OCR / STT / vision enrichment]
    E --> F[Canonicalize]
    F --> G[Persist source version]
    G --> H[Chunk / index / embed]
    H --> I[Ready]
```

Each stage SHOULD emit structured diagnostics and be independently retryable where feasible.

## 4. Acquisition

Acquisition stores enough original material to reproduce parsing:

- original uploaded bytes;
- fetched HTML and final URL metadata;
- transcript/audio/video metadata;
- connector revision identifiers;
- connector access/restriction metadata where applicable;
- source-derived reuse/export restrictions where applicable;
- MIME type and content hash;
- fetch/import timestamps.

The logical source receives an editable local display title. Changing that title MUST NOT mutate acquired bytes, upstream locator/revision metadata, canonical content or any already committed generation manifest.

Remote content SHOULD be snapshotted. Per AD-015, uploaded/local files are immutable snapshots and ordinary web URLs refresh only on explicit user action by default. A connector may auto-refresh only when it has a reliable upstream revision/change signal and access-revocation semantics. Each acquired revision has an explicit processing/readiness state; a refreshed revision MUST NOT replace a known-good retrieval-active version until the canonical representation and required retrieval indexes for that revision are ready. Connector refresh must detect access revocation/deletion: an inaccessible upstream source becomes unavailable for new retrieval and artifact generation while retaining only the metadata/version history allowed by local retention policy. Users must be able to pause/pin refreshable sources where meaningful.

## 4.1 Parser process/network/resource isolation

Document and archive parsers MUST NOT perform uncontrolled external-resource resolution while parsing untrusted inputs. Remote templates, linked images/stylesheets, external XML entities/DTDs, linked workbooks and similar references are metadata until an explicitly authorized acquisition step resolves them through the controlled fetch/connector layer. This prevents document parsing from becoming an SSRF or credential-exfiltration path.

Risky/native parsers, OCR engines, document converters, archive tools and media decoders that process attacker-controlled bytes MUST execute outside the main application process in an OS-level isolated worker/subprocess profile. That profile has no ambient application/provider secrets, no direct network path by default, a restricted service-owned input/output workspace, bounded CPU/RAM/process/file/time resources, and an explicit output allowlist/validation step before results re-enter the application. The implementation MAY use Bubblewrap or another equivalent Linux isolation mechanism; parser isolation is a security contract, not a requirement to reuse the model-code `ExecutionProvider` API.

## 5. Parsing requirements

Parsers SHOULD preserve structure instead of flattening to text. Examples:

- PDF page numbers and bounding boxes;
- DOCX headings, lists, tables and footnotes;
- PPTX slide number, text boxes, notes and images;
- spreadsheet sheet name, cells, ranges and formulas where accessible;
- HTML headings, blocks, links and tables;
- audio timestamps and speakers if diarization is available.

## 6. Enrichment

Enrichment MAY include:

- OCR for scanned pages/images;
- speech-to-text;
- speaker diarization;
- image/figure captioning and multimodal feature extraction;
- table extraction;
- language detection;
- document-level summaries;
- source classification/labels;
- Source Guide/per-source summary material;

Enrichment output must be marked as derived/model-generated where applicable rather than confused with source-authored content.

## 7. Idempotency and versioning

The same source snapshot SHOULD not be reparsed unnecessarily. Parser versions, canonical-schema version, extraction settings and enrichment versions are recorded so derived state can be invalidated and rebuilt selectively. Re-canonicalizing a retained `SourceVersion` in a way that changes node/locator identity creates a new immutable `CanonicalDocument`; referenced historical canonical representations are retained until their dependent outputs expire or are purged.

## 8. Failure handling

Acquisition/parsing must defend against decompression/archive bombs, pathological documents, password-protected/encrypted inputs, oversized embedded assets and parser hangs through explicit byte/object/time limits. Office/document macros or embedded executables MUST NOT be executed as part of ingestion. Parsers/renderers MUST disable automatic resolution of external document references, remote images/templates, linked spreadsheets and similar network resources unless acquisition is explicitly delegated to a controlled fetch/connector path. Isolation/resource-limit failures must terminate the parser job cleanly without leaving partially trusted output active.

The UI must expose partial/failed ingestion clearly. One broken page or enrichment stage SHOULD NOT necessarily invalidate an otherwise usable source. Errors should identify the stage and permit retry or fallback parser selection.
