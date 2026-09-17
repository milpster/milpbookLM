# 07 — Canonical Document Model and Provenance

## 1. Why the canonical representation is foundational

Every source type must converge to a common representation rich enough to preserve original structure and location. Retrieval, citations, source viewers and artifacts should operate primarily on this representation rather than format-specific parser output. A `CanonicalDocument` is immutable once published/used; reprocessing the same immutable `SourceVersion` with a materially different parser/canonical schema creates a new canonical representation id and atomically changes only the active pointer for future work.

## 2. CanonicalDocument

A conceptual schema:

```text
CanonicalDocument
  id
  source_version_id
  mime_type
  language
  title
  metadata
  root_nodes[]
  assets[]
  relationships[]
  parser_metadata
```

## 3. CanonicalNode

Nodes form a tree/DAG and contain:

```text
id
node_type
parent_id
children[]
text/content
semantic attributes
source_locator
layout attributes
assets[]
derivation metadata
```

Possible node types include document, section, heading, paragraph, list, list item, page, slide, table, table row/cell, figure, image, chart, code block, footnote, transcript segment and speaker turn.

## 4. Source locators

A source locator is format-specific structured location information. Examples:

### PDF
```text
page = 37
bounding_box = [x1,y1,x2,y2]
character_range = ...
```

### Audio/video
```text
start_ms = 1902120
end_ms = 1928640
speaker = "Speaker 2"
```

### Image/figure
```text
page_or_asset_id
bounding_box = [x1,y1,x2,y2]
region/figure identifier
optional OCR/text association
```

### Spreadsheet
```text
sheet = "2026 Forecast"
range = "B17:F26"
```

### Web
```text
url
DOM/block anchor
text offsets
captured revision hash
```

## 4.1 Note locators

When a note is explicitly selected as prompt context, it is citable/reproducible context. Evidence derived from a `NoteRevision` SHOULD resolve to a stable block/element identifier plus character/range coordinates within that immutable revision. A note locator must always name the exact `NoteRevision`; the mutable logical `Note` id alone is insufficient for historical evidence.

### Run/external evidence
```text
run_evidence_snapshot_id
origin_type = web_fetch | execution_output | other_tool_result
final_url / tool locator
fetched_or_created_at
content_hash
block/range/region locator where applicable
```

## 5. Provenance graph

Provenance is modeled as explicit relationships:

```text
claim -> supported_by -> evidence span
chunk -> derived_from -> canonical node
canonical node -> originates_in -> source version
note evidence -> originates_in -> exact note revision
run evidence -> captured_from -> external/tool origin snapshot
artifact element -> generated_from -> evidence set
```

This graph enables exact source jumps, claim verification, citation exports, conflict detection and audit trails.

## 6. Derived versus authoritative content

Each canonical element/evidence item MUST distinguish:

- source-authored content;
- deterministic parser transformation;
- OCR/STT output;
- model-derived caption/summary/entity;
- human-authored annotation.

Connector-supplied access/export restrictions belong to the source/source-version policy layer. Generated artifacts retain their input `SourceVersion` references, allowing export/sharing policy to re-evaluate relevant source restrictions without embedding a separate rights graph into every evidence edge.

Retrieval policies MAY prefer source-authored text over model-derived descriptions depending on task.

## 7. Stable identifiers

Within an immutable `CanonicalDocument`, canonical-node identifiers MUST remain stable. A parser/canonical-schema migration that would change node identity or locator semantics creates a new `CanonicalDocument` representation rather than rewriting the old one. Derived chunk IDs may change when chunking changes and therefore must not be used as the durable citation identity.

## 8. Citation design principle

A source citation resolves to canonical source coordinates tied to the exact retained `SourceVersion` and canonical-representation id used by the operation, never merely to a vector-search chunk. Evidence originating in an explicitly selected note resolves to an immutable `NoteRevision` locator. Agentic external/tool evidence resolves to an immutable `RunEvidenceSnapshot` unless it has been promoted to a normal `SourceVersion`. Chunks and mutable logical note ids are retrieval/UI implementation details, not durable historical citation identities.

When the entire source is the smallest meaningful evidence unit (for example an extremely short pasted source), the locator MAY resolve to the canonical document/root node rather than inventing a false fine-grained span. The UI must identify this as document-level support. This matches the reference product's documented short-source behavior while preserving an exact immutable provenance target.
