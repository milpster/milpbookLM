# v1.0 Implementation-Readiness Audit

Date: 2026-09-16. Audited input: `milpbookML-technical-implementation-guide-v1.0-FINAL.zip` against the embedded architecture v0.9 FINAL.

## Findings and resolutions

| Severity | Finding | Resolution in v1.1 |
| --- | --- | --- |
| Critical | Requirement ledger counted matching lines, not every normative occurrence, and omitted architecture-mandated component/fixture/oracle/tier/evidence fields. | Regenerated occurrence-level ledger with fingerprints, unique verification IDs and all required fields; meta-validation rejects drift or missing mappings. |
| Critical | Capability profile was a one-entry example and could not enforce AD-026 applicability. | Replaced it with a complete registry generated from every Chapter 02 parity-matrix row plus all supported source families. |
| Major | Chapter-to-chapter correspondence existed, but no section-level cross-reference proved coverage. | Added `ARCHITECTURE-CROSS-REFERENCE.md` listing every architecture heading and its binding technical destination. |
| Major | Parser, renderer, package-manager and runtime choices were too deferred for a reference implementation. | Added a reference dependency/adapter matrix with lock, license and replacement rules; expanded the ingestion matrix. |
| Major | The host Bubblewrap broker boundary lacked a concrete protocol, socket authorization and cgroup-delegation procedure. | Defined the broker request contract, peer authentication, host prerequisites and fail-closed startup checks. |
| Major | SSRF text required address pinning without saying how to prevent a second DNS lookup by the HTTP client. | Required a dedicated fetcher that connects to the validated numeric address while preserving validated Host/SNI and revalidates every redirect. |
| Major | The testing chapter mapped hundreds of requirements to broad groups rather than individually identifiable verification cases. | Each normative occurrence now has a unique test/analysis/manual ID plus group, level, fixture, oracle, tier and evidence path. |
| Moderate | UUIDv7 wording implied Python 3.13 could generate UUIDv7 natively. | PostgreSQL 18 generates database IDs with `uuidv7()`; Python-created pre-insert IDs use UUIDv4 unless an explicitly locked RFC 9562 implementation is adopted. |
| Moderate | `podman compose` provider behavior and SearXNG limiter dependency could be misread. | Pinned `podman-compose`; kept SearXNG internal-only with application budgets and made Valkey conditional on enabling SearXNG's own limiter. |
| Moderate | Security selections lacked concrete session-token, credential-encryption and HTML-isolation guidance. | Added hash-at-rest sessions, XChaCha20-Poly1305 envelope encryption/key rotation, CSP and isolated source rendering rules. |

## Audit method

The review compared all 26 same-numbered chapter pairs, every architecture heading, every normative occurrence, all 26 ADRs, the Chapter 02 parity matrix, Phase 0–7 mapping, 13 canonical E2E journeys, 10 manual scenarios, NFR numeric fixtures and exclusion lists. It additionally checked dependency claims against current primary documentation, Markdown/link/fence integrity, archive/checksum integrity and contradictions among README, decisions, chapters, changelog and review records.

## Result

All findings above are corrected in v1.1. Architecture requirements remain authoritative and are not weakened by implementation choices. No new product scope was added.
