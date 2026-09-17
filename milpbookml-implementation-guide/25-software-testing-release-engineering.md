# 25 — Executable Testing and Release Engineering

## Toolchain

- Python: pytest, pytest-asyncio, Hypothesis, coverage.py, Ruff, mypy and import-linter.
- PostgreSQL integration: real PostgreSQL/pgvector launched under rootless Podman; no SQLite substitution.
- Frontend: Vitest, Testing Library, MSW and axe-core.
- Public-boundary E2E: Playwright Test against Chromium and Firefox on GNU/Linux.
- API/schema: generated OpenAPI diff plus JSON Schema contract fixtures.
- Security: dependency/container scanning, Semgrep/Bandit-equivalent rules, hostile parser/web/sandbox corpora.
- Mutation/fault detection: mutation testing on pure policy/state/provenance code and crash/fault injection around jobs/blobs/outbox.

## Requirement ledger

`requirements.generated.json` records one entry for every individual case-insensitive normative occurrence, including multiple occurrences on one line. Each entry contains stable ID, source/line/occurrence anchor, term, full statement, normalized fingerprint, owner, implementation component, capability, verification type and unique verification ID, test level, fixture, observable oracle, execution tier, evidence path, implementation/result state and any deviation. Narrative/example occurrences are explicitly classified instead of discarded. CI reparses both numbered chapter sets, matches existing fingerprints/anchors, and fails added, removed, duplicated, renumbered or unmapped occurrences. An unimplemented SHOULD requires reviewed deviation, risk, compensation and reconsideration date.

Validate the ledger with `schemas/requirements-ledger.schema.json` and the capability profile with `schemas/capabilities.schema.json`. Schema validation is necessary but not sufficient: meta-tests also enforce exact occurrence census, ID/fingerprint uniqueness, source-anchor validity, nonempty verification contracts for normative entries, and one registry entry for every frozen Chapter 02 capability/source-family row. `ARCHITECTURE-CROSS-REFERENCE.md` is generated from the same anchors and is required to contain every architecture heading exactly once.

The generated ledger is the seed for the implementation repository, not evidence that tests already exist. `specified` means a meaningful verification contract is defined; only CI/manual evidence may change `result` to passed. Release checks reject `planned`, missing or stale evidence for every applicable stable/core requirement.

## Test-case form

Every canonical case records purpose/risk, requirement IDs, capability applicability, preconditions, fixtures, exact actions, observable oracle, forbidden side effects, tolerance, cleanup and retained evidence. Exact invariant/schema/golden/fake-provider oracles outrank human/model judgment.

## Deterministic harness

Provide fake model/media providers, fake SearXNG, local deterministic websites, connector revisions/revocations, frozen clocks/UUIDs, hostile source corpus, crash points, authorization actors and media fixtures. Ordinary CI has no paid API, public-web or personal-account dependency.

## Required E2E journeys

Preserve architecture E2E-001–E2E-013 verbatim and map every one in `requirements.generated.json`: account/notebook/source-to-citation; heterogeneous retrieval; Studio generation; notes; collaboration/sharing/copy; refresh/version races; study flows; agentic research/code; failure/reconnect/cancellation; purge/account lifecycle; provider policy/disclosure; upgrade/recovery; and multimodal/video lifecycle. All cross the public browser/API boundary. At least one release path uses production-equivalent rootless Podman packaging.

## Verification-group execution map

| Group | Primary implementation path | Canonical evidence |
| --- | --- | --- |
| `META-REQ-001`, `CAP-PROFILE-001`, `PHASE-GATE-001` | `tests/meta/` | extractor/profile/phase completeness reports |
| `ARCH-BOUNDARY-001`, `ARCH-INTEGRATION-001` | `tests/architecture/` | import graph plus production-composition integration |
| `DEPLOY-E2E-001`, `NFR-GATE-001` | `tests/deploy/`, `tests/performance/` | rootless deployment, benchmark and recovery reports |
| `DOMAIN-PROP-001`, `JOB-FAULT-001` | `tests/domain/`, `tests/faults/` | Hypothesis invariants, concurrency and crash checkpoints |
| `INGEST-GOLDEN-001`, `PROV-GOLDEN-001`, `INDEX-INTEGRATION-001` | `tests/fixtures/sources/`, `tests/indexing/` | versioned canonical/locator/index goldens |
| `RAG-E2E-001`, `EVAL-GATE-001` | `tests/e2e/grounding/`, `tests/evaluation/` | evidence/citation invariants and locked quality report |
| `PROVIDER-CONTRACT-001`, `ADAPTER-CONTRACT-001` | `tests/contracts/` | reusable adapter contract suite |
| `RESEARCH-E2E-001`, `SANDBOX-SEC-001` | `tests/e2e/research/`, `tests/security/sandbox/` | local-web research and denied-boundary evidence |
| `ARTIFACT-E2E-001`, `MEDIA-E2E-001` | `tests/e2e/studio/`, `tests/e2e/media/` | schemas, state transitions, provenance and renditions |
| `WEB-E2E-001`, `AUTHZ-MATRIX-001`, `SECURITY-SUITE-001` | `tests/e2e/web/`, `tests/security/` | Chromium/Firefox journeys, denial/enumeration/SSRF/purge |
| `MAN-MEDIA-001`, `MAN-OPS-001` | `tests/manual/` | signed versioned runbook records |
| `ADR-REVIEW-001`, `GLOSSARY-REVIEW-001`, `TEST-META-001` | `tests/meta/` | reviewed ADR/glossary consistency and mutation/fault proof |

## Manual runbook

Versioned cases cover citation viewer accuracy, responsive/accessibility behavior, audio intelligibility, realtime interruption, slides/infographics, video synchronization/legibility/captions, browser compatibility, external-provider disclosure, backup/restore operator drill and installation/upgrade. Each run records build, environment, browser/OS/hardware, tester, timestamp, result, deviations and evidence.

The repository retains architecture MAN-001–MAN-010 with their exact pass conditions. Conditional cases may be `N/A` only when `capabilities.generated.json` declares the corresponding optional/provisional capability disabled; an enabled path activates its manual gate.

## Coverage and flakiness

Coverage is diagnostic. Set high risk-specific thresholds after Phase 0 baselining; require mutation/fault evidence for authorization, state machines, provenance and purge. Quarantined flaky tests receive owner/issue/expiry and cannot remove release-gate coverage. Retries may diagnose but never convert an initial gate failure to pass.

## Release gates

Require all applicable deterministic tiers, zero unclassified requirements, zero unexplained SHOULD deviations, migrations/upgrades, SBOM/scans, signed manifest/checksums, backup restore, NFR report, manual evidence, capability profile and changelog. Optional live-provider smokes are separate and never sole contract evidence.

## Definition of done

A work item is complete only with mapped requirements, interfaces/schemas, persistence/migration, authorization/privacy, idempotency/failure semantics, observability, positive/denial/failure tests and updated conformance evidence. Every deterministic defect fix adds a regression that fails before the fix.
