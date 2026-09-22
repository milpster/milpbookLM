"""
Immutability and lifecycle triggers for content-bearing tables (FND-03).

Content versions are immutable (ch05 "Mandatory invariants"): a SourceVersion never changes
bytes/canonical document/checksum after activation; canonical documents/nodes/locators,
provenance edges (immutable endpoints, ch07), note revisions, artifact versions, manifests,
study snapshots and run evidence snapshots are immutable once created; messages and audit
events admit only their explicit privacy/append paths. The canonical_documents guard admits
one narrow exception: flipping active/activated_at (the atomic active-document swap); every
content field of that table stays immutable. Applied after create_all in the baseline
revision; drop_all removes them with the tables, so downgrade is clean.
"""

from __future__ import annotations

TRIGGER_FUNCTIONS: tuple[str, ...] = (
    """
    CREATE OR REPLACE FUNCTION milpbooklm_immutability_violation() RETURNS trigger AS $$
    BEGIN
      IF current_setting('milpbooklm.purge_context', true) = 'on' THEN
        IF TG_OP = 'DELETE' THEN
          RETURN OLD;
        END IF;
        RETURN NEW;
      END IF;
      IF TG_TABLE_NAME = 'canonical_documents'
         AND NEW.id IS NOT DISTINCT FROM OLD.id
         AND NEW.source_version_id IS NOT DISTINCT FROM OLD.source_version_id
         AND NEW.canonical_schema_version IS NOT DISTINCT FROM OLD.canonical_schema_version
         AND NEW.parser_identity IS NOT DISTINCT FROM OLD.parser_identity
         AND NEW.parser_version IS NOT DISTINCT FROM OLD.parser_version
         AND NEW.parser_profile IS NOT DISTINCT FROM OLD.parser_profile
         AND NEW.tool_versions IS NOT DISTINCT FROM OLD.tool_versions
         AND NEW.contract_json IS NOT DISTINCT FROM OLD.contract_json
         AND NEW.created_at IS NOT DISTINCT FROM OLD.created_at THEN
        RETURN NEW;
      END IF;
      RAISE EXCEPTION 'milpbooklm: % is immutable', TG_TABLE_NAME;
    END;
    $$ LANGUAGE plpgsql
    """,
    """
    CREATE OR REPLACE FUNCTION milpbooklm_source_version_activation_guard() RETURNS trigger AS $$
    BEGIN
      IF current_setting('milpbooklm.purge_context', true) = 'on' THEN
        RETURN NEW;
      END IF;
      IF OLD.activated_at IS NOT NULL
         AND (
           NEW.content_sha256 IS DISTINCT FROM OLD.content_sha256
           OR NEW.original_blob_id IS DISTINCT FROM OLD.original_blob_id
           OR NEW.content_size_bytes IS DISTINCT FROM OLD.content_size_bytes
         ) THEN
        RAISE EXCEPTION 'milpbooklm: activated source version % is immutable', OLD.id;
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
    """,
    """
    CREATE OR REPLACE FUNCTION milpbooklm_message_tombstone_guard() RETURNS trigger AS $$
    BEGIN
      IF NEW.content IS DISTINCT FROM OLD.content
         OR NEW.manifest_id IS DISTINCT FROM OLD.manifest_id
         OR NEW.role IS DISTINCT FROM OLD.role
         OR NEW.citations IS DISTINCT FROM OLD.citations
         OR (OLD.tombstone_at IS NOT NULL AND NEW.tombstone_at IS NULL) THEN
         RAISE EXCEPTION 'milpbooklm: message content is immutable; tombstone may be set once';
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
    """,
    """
    CREATE OR REPLACE FUNCTION milpbooklm_evidence_snapshot_guard() RETURNS trigger AS $$
    BEGIN
      IF NEW.origin_tool IS DISTINCT FROM OLD.origin_tool
         OR NEW.acquired_at IS DISTINCT FROM OLD.acquired_at
         OR NEW.origin_locator IS DISTINCT FROM OLD.origin_locator
         OR NEW.content_sha256 IS DISTINCT FROM OLD.content_sha256
         OR NEW.blob_id IS DISTINCT FROM OLD.blob_id
         OR NEW.locators IS DISTINCT FROM OLD.locators
         OR NEW.access_metadata IS DISTINCT FROM OLD.access_metadata THEN
         RAISE EXCEPTION 'milpbooklm: run evidence snapshot is immutable';
      END IF;
      -- Promotion is one-time (research.py: 'Set once'): NULL -> value allowed, any
      -- later change (re-promotion / un-promotion) is forbidden.
      IF OLD.promoted_source_version_id IS NOT NULL
         AND NEW.promoted_source_version_id IS DISTINCT FROM OLD.promoted_source_version_id THEN
        RAISE EXCEPTION 'milpbooklm: snapshot promotion is one-time; re-promotion is forbidden';
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
    """,
    """
    CREATE OR REPLACE FUNCTION milpbooklm_blob_finalize_guard() RETURNS trigger AS $$
    BEGIN
      IF current_setting('milpbooklm.purge_context', true) = 'on' THEN
        RETURN NEW;
      END IF;
      IF OLD.state = 'finalized' AND NEW.state <> 'finalized' THEN
        RAISE EXCEPTION 'milpbooklm: finalized blob objects may only be purged, never re-staged';
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
    """,
)

_TRIGGER_SPECS: tuple[tuple[str, str, str, str], ...] = (
    ("trg_canonical_documents_immutable", "BEFORE UPDATE OR DELETE", "canonical_documents",
     "milpbooklm_immutability_violation()"),
    ("trg_canonical_nodes_immutable", "BEFORE UPDATE OR DELETE", "canonical_nodes",
     "milpbooklm_immutability_violation()"),
    ("trg_canonical_locators_immutable", "BEFORE UPDATE OR DELETE", "canonical_locators",
     "milpbooklm_immutability_violation()"),
    ("trg_provenance_edges_immutable", "BEFORE UPDATE OR DELETE", "provenance_edges",
     "milpbooklm_immutability_violation()"),
    ("trg_note_revisions_immutable", "BEFORE UPDATE OR DELETE", "note_revisions",
     "milpbooklm_immutability_violation()"),
    ("trg_artifact_versions_immutable", "BEFORE UPDATE OR DELETE", "artifact_versions",
     "milpbooklm_immutability_violation()"),
    ("trg_generation_input_manifests_immutable", "BEFORE UPDATE OR DELETE",
     "generation_input_manifests", "milpbooklm_immutability_violation()"),
    ("trg_generation_manifest_items_immutable", "BEFORE UPDATE OR DELETE",
     "generation_manifest_items", "milpbooklm_immutability_violation()"),
    ("trg_study_session_snapshots_immutable", "BEFORE UPDATE OR DELETE", "study_session_snapshots",
     "milpbooklm_immutability_violation()"),
    ("trg_audit_events_immutable", "BEFORE UPDATE OR DELETE", "audit_events",
     "milpbooklm_immutability_violation()"),
    ("trg_source_versions_activation_guard", "BEFORE UPDATE", "source_versions",
     "milpbooklm_source_version_activation_guard()"),
    ("trg_messages_tombstone_guard", "BEFORE UPDATE", "messages",
     "milpbooklm_message_tombstone_guard()"),
    ("trg_research_evidence_snapshots_guard", "BEFORE UPDATE", "research_evidence_snapshots",
     "milpbooklm_evidence_snapshot_guard()"),
    ("trg_blob_objects_finalize_guard", "BEFORE UPDATE", "blob_objects",
     "milpbooklm_blob_finalize_guard()"),
)

TRIGGER_DDL: tuple[str, ...] = tuple(
    f"CREATE TRIGGER {name} {timing} ON {table} FOR EACH ROW EXECUTE FUNCTION {function}"
    for name, timing, table, function in _TRIGGER_SPECS
)

DROP_TRIGGER_DDL: tuple[str, ...] = tuple(
    f"DROP TRIGGER IF EXISTS {name} ON {table}" for name, _, table, _ in _TRIGGER_SPECS
)

def drop_triggers_sql() -> list[str]:
    """Idempotent DDL removing every guard (used before re-apply in rehearsals)."""
    return [f"DROP TRIGGER IF EXISTS {name} ON {table}" for name, _, table, _ in _TRIGGER_SPECS] + [
        "DROP FUNCTION IF EXISTS milpbooklm_immutability_violation()",
        "DROP FUNCTION IF EXISTS milpbooklm_source_version_activation_guard()",
        "DROP FUNCTION IF EXISTS milpbooklm_message_tombstone_guard()",
        "DROP FUNCTION IF EXISTS milpbooklm_evidence_snapshot_guard()",
        "DROP FUNCTION IF EXISTS milpbooklm_blob_finalize_guard()",
    ]
