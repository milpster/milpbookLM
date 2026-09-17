# 02 — Capability and Parity Implementation Matrix

## Capability registry

Use the included complete `capabilities.generated.json` as the seed for `packages/contracts/capabilities.yaml`. Every Chapter 02 parity-matrix row and source family has an entry with stable ID, classification, phase, dependencies, feature flag, tests and reference text. CI reparses the frozen architecture table and fails if a row/family is absent or duplicated; the checked-in registry is reviewed, not silently overwritten.

`classification` expresses the local release obligation; `reference_maturity` records how Google currently documents the behavior. Thus agentic chat remains a required Phase 3 target while honestly marked `experimental/documented`, and provider-limited behavior is never advertised unless its dependency profile is enabled.

Core capabilities include notebook/source management, supported source families, grounded chat/citations, notes, sharing/collaboration, responsive UI and the core Studio artifact families, including Interactive Learning Overview. Advanced/provider-dependent capabilities include interactive/Cinematic media paths. Recorded-audio capture, general realtime notebook voice and the remaining announcement-only study/note behaviors remain provisional. Public notebooks and selected late Studio variants remain optional. Native mobile apps, Google ecosystem coupling and pixel-perfect UI cloning are non-targets.

## Source families

Adapters must cover uploaded/pasted text and Markdown, PDF, DOCX, PPTX, CSV/spreadsheets, EPUB, HTML/web snapshots, images/OCR, audio/transcripts, video, transcript-backed public-video URLs, connector snapshots and internal/generated sources. Connectors use the same snapshot/version contract and may be disabled independently.

## Feature gating

The backend computes effective capability state from compiled support, administrator policy, configured providers and dependency health. The frontend consumes `/api/v1/capabilities`; it must not infer availability from hidden buttons or provider names. Enabling a capability activates its security, privacy, lifecycle and test obligations.

## Parity verification

Maintain `tests/parity/capabilities.md` with architecture mapping, reproducible reference observation date and local acceptance evidence. Reference-product changes create review issues; they do not silently alter local behavior.
