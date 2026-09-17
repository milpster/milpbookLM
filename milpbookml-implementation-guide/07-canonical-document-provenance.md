# 07 — Canonical Document and Provenance Contracts

## Representation

Serialize `CanonicalDocument` as versioned JSON with `schema_version`, `document_id`, `source_version_id`, parser identity/version, content language(s), metadata, root-node IDs and ordered `CanonicalNode`s. A node has `node_id`, `kind`, parent/child order, normalized text, structural path, source locator, optional geometry/time span/table cells/media reference, language, authority class and derivation records. Unknown future fields are ignored on read but preserved on round trip where supported.

Node kinds are a closed versioned set for each schema revision: document, section, paragraph, heading, list/list-item, quote, code, table/row/cell, image/figure/caption, page/slide/sheet, transcript-segment/speaker-turn and attachment/reference. Adapters map unsupported structures to an explicit generic node plus original metadata rather than discarding them.

## Stable IDs

Derive node IDs from source-version ID plus parser-stable structural identity, never display order alone. Chunk IDs derive from canonical node IDs, chunker revision and span. Reprocessing with the same versions must reproduce identifiers.

## Locators

PDF locators include page plus normalized bounding boxes/text span; audio/video locators include millisecond ranges and transcript-speaker references; spreadsheets include sheet and cell/range; web locators include canonical URL, captured retrieval timestamp and DOM/heading path; images include region; notes pin `NoteRevision`; run evidence pins immutable evidence record.

## Provenance graph

Store typed edges `derived_from`, `quotes`, `summarizes`, `transforms`, `generated_from` and `contains`. Traversal must be bounded and cycle-safe. Effective restrictions are computed across content-bearing ancestors and cached only with all policy/version inputs in the key.

Persist provenance edges in normalized rows (`from_type/id/version`, `edge_type`, `to_type/id/version`, locator, transform identity/version, confidence and created-at). Enforce immutable endpoints and uniqueness. Purge traversal uses these rows plus manifest/blob/cache ownership edges; vector similarity is never used to infer deletion dependencies.

## Validation

JSON Schema validation and locator-specific semantic validation precede persistence. Golden round-trip tests, stability tests across repeated parsing and citation jump tests are release gates.
