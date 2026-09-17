# 06 — Source Ingestion Implementation

## Pipeline

`acquire -> quarantine -> identify -> parse -> canonicalize -> enrich -> chunk -> index -> activate`. Every stage is an idempotent job keyed by source-version and pipeline revision. Activation is one transaction after required artifacts exist.

## Acquisition

Stream uploads to quarantine while enforcing byte limits and SHA-256; never trust filenames, extensions or client MIME. URL acquisition uses the hardened fetch service from Chapter 19. Connector acquisitions record upstream identity/revision and restriction metadata. Duplicate content may share immutable blobs but never ownership or ACL rows.

## Parser isolation

Run each parser in a separate rootless worker subprocess/container with read-only runtime, empty temporary directory, CPU/memory/time/output limits and no network. LibreOffice, PDF tooling, OCR and FFmpeg never execute inside API workers. Store tool versions and parser profile with results.

## Failure and retry

Stable errors distinguish unsupported, corrupt, encrypted, too large, timeout, policy-blocked and internal failure. Retry only transient failures. Preserve the prior active version on refresh failure. Cleanup incomplete temporary objects through the blob reconciliation protocol.

## Idempotency

An acquisition key combines source, requested upstream revision/content hash and importer version. Repeated commands return the existing operation unless the caller explicitly requests reprocessing with a new pipeline revision.

## Fixtures

The golden corpus includes benign and hostile PDFs, DOCX/PPTX/XLSX, HTML, images, audio/video, malformed archives, decompression bombs, external-reference documents, multilingual/RTL text and locator assertions.

## Reference adapter matrix

Use the concrete parser/tool selections in `REFERENCE-DEPENDENCIES.md`. Each adapter declares accepted media types, sniffing rules, compressed/uncompressed/pixel/duration limits, parser image digest, canonical-schema version and locator guarantees. Unsupported formulas/macros, encrypted inputs, missing transcripts and OCR failures remain explicit source-version states; adapters never return an apparently successful empty document for a failed parse.

Spreadsheet ingestion stores displayed/cached values and formulas as distinct fields and does not claim to evaluate arbitrary workbooks. Public-video URL ingestion imports an available transcript and metadata through a compliant adapter; it does not bypass access controls, download protected media or promise a transcript where none is lawfully available.
