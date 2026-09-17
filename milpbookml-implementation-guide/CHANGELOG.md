# Implementation Guideline Changelog

## v1.2 FINAL — 2026-09-16

- Re-audited the package from an implementation-planning-agent perspective and added `PLANNING-HANDOFF.md` with workstream dependencies, critical path, phase gates, decision deadlines, planning procedure and definitions of ready/complete.
- Added `PARITY-SCOPE-AUDIT.md` to distinguish direct parity, necessary self-hosting improvements, vendor-neutral mappings, provisional/optional work and deliberate non-targets.
- Promoted Interactive Learning Overview to stable Phase 4 parity after current official Reports documentation satisfied the architecture's promotion criterion; embedded architecture is now v0.10 FINAL.
- Corrected capability phase assignments for notes, basic Source Guide and Phase 1 PDF/text ingestion.
- Corrected the capability JSON Schema to accept every real classification and string priority, and added planning-workstream/reference-maturity fields.
- Marked documented agentic chat as experimental reference behavior without removing it from the Phase 3 parity target.
- Revalidated traceability, scope exclusions, official feature behavior, manifests and archive integrity.

## v1.1 FINAL — 2026-09-16

- Re-audited every technical chapter against every architecture chapter/heading and added a section-level cross-reference.
- Replaced the line-level/coarse requirements ledger with occurrence-level records and architecture-mandated component, fixture, oracle, tier and evidence fields.
- Replaced the one-entry capability example with a complete Chapter 02 capability/source-family registry.
- Added JSON Schemas for both generated registries and made unimplemented/not-run state explicit.
- Added concrete dependency, parser and renderer selections plus frozen-lock rules.
- Corrected UUIDv7 guidance for Python 3.13/PostgreSQL 18.
- Made the host execution broker, SSRF destination pinning, sessions, secret encryption and source-HTML/browser isolation actionable.
- Preserved all v0.9 architecture requirements, 13 automated E2E journeys, 10 manual scenarios and scope exclusions.

## v1.0 FINAL — 2026-09-16

- Derived one-to-one from architecture v0.9 FINAL.
- Froze Python/FastAPI and React/TypeScript as the normative application stack.
- Froze rootless Podman Compose on GNU/Linux as the first deployment target.
- Froze SearXNG plus hardened fetch plus Playwright as web-research baseline.
- Explicitly excluded BrowserOS from normative dependencies and capabilities.
- Specified domain/persistence, jobs/outbox, blob consistency, API/SSE, security, authorization, purge, media and testing implementations.
- Preserved architecture capabilities, phases, NFRs, multimodal/video behavior and verification obligations.
