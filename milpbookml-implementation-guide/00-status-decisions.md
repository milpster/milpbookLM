# 00 — Status, Decisions and Normative Implementation Profile

## Stable requirement identifiers

Architecture requirements are assigned `ARCH-CC-NNN`; technical requirements use `TECH-CC-NNN`, where `CC` is the two-digit chapter. IDs never change meaning. Deleted requirements remain tombstoned. `tools/spec/extract_requirements.py` scans numbered chapters case-insensitively for MUST/SHOULD terms and fails CI on unclassified occurrences.

## Frozen implementation decisions

| ID | Decision |
| --- | --- |
| TAD-001 | Python 3.13/FastAPI backend and React 19/TypeScript frontend |
| TAD-002 | Rootless `podman compose` with a pinned `podman-compose` provider is the first supported production packaging |
| TAD-003 | PostgreSQL 18 + pgvector is the only mandatory data service |
| TAD-004 | Filesystem blob backend is default; S3-compatible storage remains a port |
| TAD-005 | PostgreSQL leases/outbox implement initial jobs and events |
| TAD-006 | SearXNG is the default zero-key search-discovery adapter |
| TAD-007 | Playwright is the sole normative browser automation adapter |
| TAD-008 | Bubblewrap/cgroup v2 implements local code isolation |
| TAD-009 | OpenAPI 3.1 and versioned JSON Schema define public contracts |
| TAD-010 | pytest/Vitest/Playwright Test are the reference test runners |
| TAD-011 | CPython 3.13 uses PostgreSQL 18 `uuidv7()` for database-generated ordered IDs; pre-insert application IDs use UUIDv4 unless a locked RFC 9562 library is approved |
| TAD-012 | Node.js 24 LTS + pnpm and `uv` are the normative dependency-management lines; exact patches live in locks/digests |

## Version floors

Pin exact patch versions in `uv.lock`, `pnpm-lock.yaml` and container digests. Version numbers here are compatibility floors, not permission to float production dependencies. CI installs frozen locks and records tool/browser/native-binary versions. An automated weekly dependency job proposes locked upgrades; security-critical parser, Chromium and Bubblewrap updates bypass the normal monthly cadence.

## Conformance profile

Each build emits `conformance.json` with capability ID, architecture classification, implementation status, enabled state, dependencies, automated tests and manual tests. Stable/core capabilities may not be `not_applicable`. Disabled optional features remain visible as disabled and must not be advertised.

## BrowserOS disposition

BrowserOS is not a dependency, supported provider or parity commitment. A future adapter may be evaluated through the same `BrowserProvider` contract only after Linux, multi-user isolation, licensing, security and deterministic-test requirements are satisfied.
