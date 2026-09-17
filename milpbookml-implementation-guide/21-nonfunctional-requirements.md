# 21 — Measurable Non-Functional Acceptance

## Reference profile

Unless a release publishes a reviewed replacement profile, test on one GNU/Linux x86-64 or ARM64 host with 8 CPU cores, 16 GiB RAM and SSD/NVMe sustaining at least 500 MB/s sequential read/write; local PostgreSQL/filesystem blobs; one API process; and at least two ordinary worker slots. Seed 25 users, 250 notebooks, 5,000 retained source versions, 2 million retrieval chunks and 20,000 artifact/message/note records. The backup envelope is at most 50 GiB PostgreSQL plus 200 GiB blobs. Publish exact kernel, architecture, Podman, PostgreSQL, model/provider and fixture/tool versions with every result.

## Reliability and integrity

No acknowledged metadata mutation may be lost after process restart. Crash tests cover upload finalization, source activation, job checkpoints, outbox dispatch and artifact publication. Concurrency tests prove optimistic locking and ownership invariants.

## Performance

Run the non-model workload for at least ten minutes after documented warm-up with 10 concurrent authenticated clients and a representative 90% read/10% write mix. Ordinary authenticated metadata/resource reads and writes target p95 <= 500 ms. Persisted job-state transitions reach a continuously connected browser within 2 seconds p95 over at least 1,000 transitions; reconnect/resynchronization is measured separately. Provider/model/search time and upload/download transfer are excluded only where the architecture permits. Streaming-capable generation exposes incremental output without application-level full-response buffering. Heavy parsing, research and media remain asynchronous. Additional retrieval/queue gates may be tightened from measured Phase 1 baselines; relaxation requires an ADR and regression evidence.

## Portability and scale

Support a single rootless GNU/Linux host first on the published x86-64 or ARM64 reference architecture. A release claims an architecture only when its packaging, integration and release-gate evidence ran there. Scale workers horizontally only where job leases and blob access preserve correctness.

## Accessibility

Target WCAG 2.2 AA for core workflows. Axe automation is necessary but manual keyboard, screen-reader, zoom/reflow, contrast and media-caption checks remain release evidence.

## Backup/restore

Meet RPO <= 24 hours and RTO <= 4 hours for the reference envelope. Back up PostgreSQL consistently with blob inventory/version metadata and encrypted secrets needed for restore. Quarterly automated restore rehearsals and release-candidate operator drills must pass integrity/readiness checks.

The local-filesystem protocol exploits immutable finalized blobs: take/retain a blob snapshot or copy that includes every object referenced by the chosen consistent PostgreSQL backup, and tolerate extra unreferenced objects. Physical blob GC observes a safety delay longer than the maximum backup-copy window so it cannot remove an object needed by the selected DB snapshot. The backup manifest records DB recovery point, blob inventory root/hash, application/schema version and master-key recovery material location. Restore verifies every referenced blob before readiness; missing objects are integrity failures, while indexes may rebuild in an explicitly degraded state.

## Supply chain and operability

Lock dependencies/container digests, emit CycloneDX SBOM, scan vulnerabilities and sign release artifacts where infrastructure permits. Liveness/readiness and capability diagnostics must distinguish mandatory failure from optional degradation.
