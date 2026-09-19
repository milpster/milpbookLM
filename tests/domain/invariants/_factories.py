"""Row factories for the FND-03 database invariant tests.

TAD-011: every row is pre-inserted with ``uuid.uuid4()`` - the database-side
``uuidv7()`` defaults are exercised by the tests that omit ``id``, and no UUIDv7 is ever
generated in Python. Inserted rows are tracked for LIFO cleanup so each test leaves the
shared test database clean (children registered after a parent are deleted first, which
satisfies the RESTRICT foreign keys). Rows of the fully-immutable tables cannot be
deleted by the app role (BEFORE UPDATE OR DELETE triggers), so their cleanup is skipped;
each test addresses only its own generated ids, so residuals never interfere.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import psycopg

# A sha256 hex digest is 64 characters (checksum-length asserts).
SHA256_HEX_LEN = 64

# Tables with BEFORE UPDATE OR DELETE immutability triggers: the app role cannot DELETE
# their rows, so tracked cleanup for them is skipped (residual rows are harmless).
IMMUTABLE_TABLES = frozenset({
    "canonical_documents",
    "canonical_nodes",
    "canonical_locators",
    "note_revisions",
    "artifact_versions",
    "generation_input_manifests",
    "generation_manifest_items",
    "study_session_snapshots",
    "audit_events",
})


def _cleanup_table(sql: str) -> str | None:
    _, sep, table = sql.partition(" FROM ")
    if not sep:
        return None
    return table.split()[0]


class Db:
    """Thin autocommit wrapper around a psycopg connection with LIFO tracked cleanup."""

    def __init__(self, dsn: str) -> None:
        self.conn = psycopg.connect(dsn, autocommit=True)
        self._cleanups: list[Callable[[], None]] = []

    def track(self, sql: str, params: tuple[object, ...] = ()) -> None:
        if _cleanup_table(sql) in IMMUTABLE_TABLES:
            return
        self._cleanups.append(lambda: self.conn.execute(sql, params))

    def cleanup(self) -> None:
        while self._cleanups:
            self._cleanups.pop()()

    def close(self) -> None:
        self.cleanup()
        self.conn.close()

    # -- identity -----------------------------------------------------------

    def user(self, *, status: str = "active") -> uuid.UUID:
        uid = uuid.uuid4()
        self.conn.execute(
            "INSERT INTO users (id, email, display_name, password_hash, status) "
            "VALUES (%s, %s, %s, %s, %s)",
            (uid, f"user-{uid.hex[:20]}@example.invalid", "Test User", "hash", status),
        )
        self.track("DELETE FROM users WHERE id = %s", (uid,))
        return uid

    # -- collaboration ------------------------------------------------------

    def notebook(
        self,
        owner: uuid.UUID,
        *,
        title: str = "NB",
        custody_state: str = "none",
        sharing_state: str = "private",
        owner_membership: bool = True,
    ) -> uuid.UUID:
        nid = uuid.uuid4()
        self.conn.execute(
            "INSERT INTO notebooks (id, title, created_by_user_id, custody_state, "
            "sharing_state, owner_user_id) VALUES (%s, %s, %s, %s, %s, %s)",
            (nid, title, owner, custody_state, sharing_state, owner),
        )
        self.track("DELETE FROM notebooks WHERE id = %s", (nid,))
        if owner_membership:
            self.membership(nid, owner, "owner")
        return nid

    def membership(self, notebook_id: uuid.UUID, user_id: uuid.UUID, role: str) -> uuid.UUID:
        mid = uuid.uuid4()
        self.conn.execute(
            "INSERT INTO notebook_memberships (id, notebook_id, user_id, role, granted_by_user_id) "
            "VALUES (%s, %s, %s, %s, %s)",
            (mid, notebook_id, user_id, role, user_id),
        )
        self.track("DELETE FROM notebook_memberships WHERE id = %s", (mid,))
        return mid

    # -- sources ------------------------------------------------------------

    def source(
        self, notebook_id: uuid.UUID, created_by: uuid.UUID, *, availability: str = "active"
    ) -> uuid.UUID:
        sid = uuid.uuid4()
        self.conn.execute(
            "INSERT INTO sources (id, notebook_id, type, origin, display_title, availability, "
            "created_by_user_id) VALUES (%s, %s, 'plain_text', %s, 'Src', %s, %s)",
            (sid, notebook_id, f"origin://{sid.hex[:16]}", availability, created_by),
        )
        self.track("DELETE FROM sources WHERE id = %s", (sid,))
        return sid

    def source_version(
        self,
        source_id: uuid.UUID,
        created_by: uuid.UUID,
        *,
        version_number: int = 1,
        status: str = "active",
        sha256: str | None = None,
    ) -> uuid.UUID:
        vid = uuid.uuid4()
        digest = sha256 or (vid.hex * 2)[:64]
        activated = datetime.now(UTC) if status == "active" else None
        self.conn.execute(
            "INSERT INTO source_versions (id, source_id, version_number, content_sha256, status, "
            "activated_at, created_by_user_id) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (vid, source_id, version_number, digest, status, activated, created_by),
        )
        self.track("DELETE FROM source_versions WHERE id = %s", (vid,))
        return vid

    def canonical_document(
        self, source_version_id: uuid.UUID, *, active: bool = False
    ) -> uuid.UUID:
        did = uuid.uuid4()
        self.conn.execute(
            "INSERT INTO canonical_documents (id, source_version_id, canonical_schema_version, "
            "parser_version, active, activated_at) VALUES (%s, %s, '1', '1', %s, %s)",
            (did, source_version_id, active, None if not active else datetime.now(UTC)),
        )
        self.track("DELETE FROM canonical_documents WHERE id = %s", (did,))
        return did

    # -- studio ---------------------------------------------------------------

    def note(
        self,
        notebook_id: uuid.UUID,
        created_by: uuid.UUID,
        *,
        kind: str = "user",
        editable: bool = True,
        title: str = "Note",
    ) -> uuid.UUID:
        nid = uuid.uuid4()
        self.conn.execute(
            "INSERT INTO notes (id, notebook_id, kind, editable, title, created_by_user_id) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (nid, notebook_id, kind, editable, title, created_by),
        )
        self.track("DELETE FROM notes WHERE id = %s", (nid,))
        return nid

    def note_revision(
        self,
        note_id: uuid.UUID,
        author: uuid.UUID,
        *,
        revision_number: int = 1,
        content: dict[str, object] | None = None,
        provenance_refs: str | None = None,
        content_dependencies: str = "[]",
    ) -> uuid.UUID:
        rid = uuid.uuid4()
        payload = content or {"blocks": [{"type": "paragraph", "text": "hello"}]}
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(serialized.encode()).hexdigest()
        self.conn.execute(
            "INSERT INTO note_revisions (id, note_id, revision_number, content, content_sha256, "
            "author_user_id, provenance_refs, content_dependencies) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                rid,
                note_id,
                revision_number,
                json.dumps(payload),
                digest,
                author,
                provenance_refs,
                content_dependencies,
            ),
        )
        self.track("DELETE FROM note_revisions WHERE id = %s", (rid,))
        return rid

    def artifact(
        self, notebook_id: uuid.UUID, created_by: uuid.UUID, *, artifact_type: str = "report"
    ) -> uuid.UUID:
        aid = uuid.uuid4()
        self.conn.execute(
            "INSERT INTO artifacts (id, notebook_id, artifact_type, created_by_user_id) VALUES"
                " (%s, %s, %s, %s)",
            (aid, notebook_id, artifact_type, created_by),
        )
        self.track("DELETE FROM artifacts WHERE id = %s", (aid,))
        return aid

    def artifact_version(
        self,
        artifact_id: uuid.UUID,
        manifest_id: uuid.UUID,
        created_by: uuid.UUID,
        *,
        version_number: int = 1,
    ) -> uuid.UUID:
        vid = uuid.uuid4()
        self.conn.execute(
            "INSERT INTO artifact_versions (id, artifact_id, version_number, recipe_version, "
            "manifest_id, created_by_user_id) VALUES (%s, %s, %s, '1', %s, %s)",
            (vid, artifact_id, version_number, manifest_id, created_by),
        )
        self.track("DELETE FROM artifact_versions WHERE id = %s", (vid,))
        return vid

    def user_artifact_state(self, user_id: uuid.UUID, artifact_version_id: uuid.UUID) -> uuid.UUID:
        sid = uuid.uuid4()
        self.conn.execute(
            "INSERT INTO user_artifact_state (id, user_id, artifact_version_id) VALUES (%s, %s,"
                " %s)",
            (sid, user_id, artifact_version_id),
        )
        self.track("DELETE FROM user_artifact_state WHERE id = %s", (sid,))
        return sid

    def study_snapshot(
        self,
        user_id: uuid.UUID,
        artifact_version_id: uuid.UUID,
        source_state_id: uuid.UUID,
        *,
        snapshot: str | None = None,
    ) -> uuid.UUID:
        sid = uuid.uuid4()
        self.conn.execute(
            "INSERT INTO study_session_snapshots (id, user_id, artifact_version_id,"
                " source_state_id, snapshot) "
            "VALUES (%s, %s, %s, %s, %s)",
            (sid, user_id, artifact_version_id, source_state_id, snapshot or '{"progress": 0.5}'),
        )
        self.track("DELETE FROM study_session_snapshots WHERE id = %s", (sid,))
        return sid

    # -- manifests ------------------------------------------------------------

    def manifest(
        self,
        *,
        op_kind: str = "ordinary_chat",
        notebook_id: uuid.UUID | None = None,
        created_by: uuid.UUID | None = None,
        parent_manifest_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        mid = uuid.uuid4()
        self.conn.execute(
            "INSERT INTO generation_input_manifests (id, notebook_id, created_by_user_id, op_kind, "
            "config_snapshot, parent_manifest_id) VALUES (%s, %s, %s, %s, %s, %s)",
            (
                mid,
                notebook_id,
                created_by,
                op_kind,
                '{"instructions": null, "mode": "ordinary"}',
                parent_manifest_id,
            ),
        )
        self.track("DELETE FROM generation_input_manifests WHERE id = %s", (mid,))
        return mid

    # -- conversation -----------------------------------------------------------

    def conversation(
        self,
        owner: uuid.UUID,
        *,
        notebook_id: uuid.UUID | None = None,
        visibility: str = "private",
    ) -> uuid.UUID:
        cid = uuid.uuid4()
        self.conn.execute(
            "INSERT INTO conversations (id, owner_user_id, notebook_id, visibility) VALUES (%s,"
                " %s, %s, %s)",
            (cid, owner, notebook_id, visibility),
        )
        self.track("DELETE FROM conversations WHERE id = %s", (cid,))
        return cid

    def message(
        self,
        conversation_id: uuid.UUID,
        manifest_id: uuid.UUID,
        *,
        sender: uuid.UUID | None = None,
        role: str = "user",
        content: str = "hello",
        citations: str | None = None,
    ) -> uuid.UUID:
        mid = uuid.uuid4()
        self.conn.execute(
            "INSERT INTO messages (id, conversation_id, sender_user_id, role, content,"
                " manifest_id, citations) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (mid, conversation_id, sender, role, content, manifest_id, citations),
        )
        self.track("DELETE FROM messages WHERE id = %s", (mid,))
        return mid

    # -- research / blobs ---------------------------------------------------------

    def research_run(
        self, notebook_id: uuid.UUID, user: uuid.UUID, *, visibility: str = "private"
    ) -> uuid.UUID:
        rid = uuid.uuid4()
        self.conn.execute(
            "INSERT INTO research_runs (id, notebook_id, initiated_by_user_id, visibility, goal) "
            "VALUES (%s, %s, %s, %s, 'goal')",
            (rid, notebook_id, user, visibility),
        )
        self.track("DELETE FROM research_runs WHERE id = %s", (rid,))
        return rid

    def evidence_snapshot(
        self,
        run_id: uuid.UUID,
        *,
        retention_policy: str | None = None,
        blob_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        eid = uuid.uuid4()
        self.conn.execute(
            "INSERT INTO research_evidence_snapshots (id, run_id, origin_tool, acquired_at,"
                " content_sha256, retention_policy, blob_id) "
            "VALUES (%s, %s, 'web_fetch', now(), %s, %s, %s)",
            (eid, run_id, (eid.hex * 2)[:64], retention_policy, blob_id),
        )
        self.track("DELETE FROM research_evidence_snapshots WHERE id = %s", (eid,))
        return eid

    def blob(self, *, state: str = "staging", sha256: str | None = None) -> uuid.UUID:
        bid = uuid.uuid4()
        digest = sha256 or (bid.hex * 2)[:64]
        self.conn.execute(
            "INSERT INTO blob_objects (id, content_sha256, size_bytes, storage_path, state,"
                " finalized_at) "
            "VALUES (%s, %s, 10, %s, %s, %s)",
            (
                bid,
                digest,
                f"blobs/{bid}",
                state,
                None if state != "finalized" else datetime.now(UTC),
            ),
        )
        self.track("DELETE FROM blob_objects WHERE id = %s", (bid,))
        return bid
