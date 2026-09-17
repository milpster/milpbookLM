# 05 — Domain and Persistence Model

## Identifier and concurrency rules

Use PostgreSQL `uuid` primary keys and UTC `timestamptz`. PostgreSQL 18 `uuidv7()` is the database default for persisted aggregate/version IDs. Python 3.13 does not natively generate UUIDv7, so commands that require an identifier before insert use UUIDv4 unless the project adopts and locks a reviewed RFC 9562 implementation; clients must treat both as opaque UUIDs. Mutable roots carry integer `revision` and use `If-Match`/ETag compare-and-swap updates. Content versions are immutable and outbox events commit in the same transaction.

Foreign keys, uniqueness, check constraints and partial unique indexes enforce invariants where PostgreSQL can express them. Service logic plus serializable/advisory-lock sections protect cross-row rules such as final-owner removal, active-version swap and idempotency-key creation. Deadlock/serialization failures use bounded whole-transaction retries.

## Core tables

Create normalized tables for users/sessions, notebooks/memberships, sources/source_versions/source_restrictions, canonical_documents/nodes/locators, conversations/messages, notes/note_revisions, artifacts/artifact_versions/user_artifact_state/study_session_snapshots, generation_input_manifests/manifest_items, research_runs/run_steps/evidence_snapshots, jobs/job_attempts, outbox_events, idempotency_keys, provider_configs/credentials, connector_configs/credentials, share_links, notifications, audit_events, blob_objects/references and purge_tasks.

## Mandatory invariants

- Every notebook has at least one owner or an explicit locked administrative-custody state.
- A `SourceVersion` never changes bytes, canonical document or checksum after activation.
- Retrieval uses only the atomic active version and applicable ACL/restriction state.
- Messages, note revisions and artifact versions pin the exact generation manifest.
- Private conversation/research/tool traces never become notebook-shared implicitly.
- Derived objects retain version-pinned provenance and effective restriction inputs.

## Migrations

Each Alembic revision is forward-safe, restartable where possible and accompanied by migration tests from the previous supported release. Large backfills use resumable jobs rather than long blocking transactions.

## Tests

Property tests exercise ownership, role transitions, immutable versions, manifest stability and effective-policy propagation. PostgreSQL constraint tests prove invariants under concurrent transactions.
