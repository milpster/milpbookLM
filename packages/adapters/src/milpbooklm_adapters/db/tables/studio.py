"""
Studio tables (ch05 "notes/artifacts/study").

Notes, note revisions, artifacts, artifact versions, user artifact state
and study session snapshots.

Separation invariants (architecture ch05 §11, ARCH-05-007..014):
* Note (mutable) != NoteRevision (immutable); a revision is a content snapshot;
* Artifact (mutable) != ArtifactVersion (immutable); versions pin the exact manifest;
* UserArtifactState is mutable per-user interaction state, separate from shared artifact
  content - one user's study actions never touch another user's rows (unique per pair)
  and never create artifact versions;
* StudySessionSnapshot is an immutable, user-private materialization of state + version.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from ._common import (
    METADATA,
    created_at,
    etag_column,
    revision_column,
    updated_at,
    uuid_fk,
    uuid_pk,
)

notes = sa.Table(
    "notes",
    METADATA,
    uuid_pk(),
    uuid_fk("notebook_id", "notebooks", ondelete="CASCADE"),
    sa.Column(
        "kind",
        sa.Text,
        nullable=False,
        server_default=sa.text("'user'"),
    ),
    # Editability policy (ARCH-05-007): user-authored notes are editable; a saved
    # chat-response note may be immutable after creation.
    sa.Column("editable", sa.Boolean, nullable=False, server_default=sa.text("true")),
    sa.Column("title", sa.Text, nullable=False),
    uuid_fk("current_revision_id", "note_revisions", nullable=True, ondelete="SET NULL"),
    uuid_fk("created_by_user_id", "users"),
    revision_column(),
    etag_column(),
    created_at(),
    updated_at(),
    sa.CheckConstraint(
        "kind IN ('user', 'saved_chat_response', 'derived_from_source')",
        name="ck_notes_kind",
    ),
)

note_revisions = sa.Table(
    "note_revisions",
    METADATA,
    uuid_pk(),
    uuid_fk("note_id", "notes", ondelete="CASCADE"),
    sa.Column("revision_number", sa.Integer, nullable=False),
    # Rich structure (tables, inline citations) preserved as structured content.
    sa.Column("content", JSONB, nullable=False),
    sa.Column("content_sha256", sa.Text, nullable=False),
    uuid_fk("author_user_id", "users"),
    sa.Column("provenance_refs", JSONB, nullable=True),
    sa.Column("attachments", JSONB, nullable=True),
    # ARCH-05-010: system-generated/source-derived note content MUST retain its exact
    # content dependencies so AD-016 purge traversal stays enforceable.
    sa.Column("content_dependencies", JSONB, nullable=False, server_default=sa.text("'[]'")),
    created_at(),
    sa.UniqueConstraint("note_id", "revision_number", name="uq_note_revisions_note_number"),
    sa.CheckConstraint("revision_number > 0", name="ck_note_revisions_number"),
)

artifacts = sa.Table(
    "artifacts",
    METADATA,
    uuid_pk(),
    uuid_fk("notebook_id", "notebooks", ondelete="CASCADE"),
    sa.Column(
        "artifact_type",
        sa.Text,
        nullable=False,
    ),
    uuid_fk("current_version_id", "artifact_versions", nullable=True, ondelete="SET NULL"),
    sa.Column(
        "status",
        sa.Text,
        nullable=False,
        server_default=sa.text("'draft'"),
    ),
    uuid_fk("created_by_user_id", "users"),
    revision_column(),
    etag_column(),
    created_at(),
    updated_at(),
    sa.CheckConstraint(
        "status IN ('draft', 'generating', 'validating', 'ready', 'failed', 'cancelled', "
        "'out_of_date')",
        name="ck_artifacts_status",
    ),
    sa.CheckConstraint(
        "artifact_type IN ('report', 'table', 'mind_map', 'flashcards', 'quiz', 'slide_deck', "
        "'infographic', 'audio_overview', 'video_overview', 'composite')",
        name="ck_artifacts_type",
    ),
)

artifact_versions = sa.Table(
    "artifact_versions",
    METADATA,
    uuid_pk(),
    uuid_fk("artifact_id", "artifacts", ondelete="CASCADE"),
    sa.Column("version_number", sa.Integer, nullable=False),
    sa.Column("recipe_version", sa.Text, nullable=False),
    sa.Column("recipe", JSONB, nullable=True),
    # The exact pinned manifest (ARCH-05-015); evidence/content dependencies are the basis
    # for AD-023 effective access checks and AD-016 purge traversal.
    uuid_fk("manifest_id", "generation_input_manifests", ondelete="RESTRICT"),
    sa.Column("evidence_dependencies", JSONB, nullable=False, server_default=sa.text("'[]'")),
    sa.Column("model_metadata", JSONB, nullable=True),
    sa.Column("structured_representation", JSONB, nullable=True),
    sa.Column("rendered_blob_ids", JSONB, nullable=True),
    # Composite artifacts reference exact versions of other artifacts (version-pinned).
    sa.Column("composite_dependencies", JSONB, nullable=True),
    uuid_fk("created_by_user_id", "users"),
    created_at(),
    sa.UniqueConstraint(
        "artifact_id", "version_number", name="uq_artifact_versions_artifact_number"
    ),
    sa.CheckConstraint("version_number > 0", name="ck_artifact_versions_number"),
)

user_artifact_state = sa.Table(
    "user_artifact_state",
    METADATA,
    uuid_pk(),
    uuid_fk("user_id", "users", ondelete="CASCADE"),
    uuid_fk("artifact_version_id", "artifact_versions", ondelete="CASCADE"),
    # Current position, got-it/missed-it answers, scores, retry sets, completion timestamps.
    sa.Column("state", JSONB, nullable=False, server_default=sa.text("'{}'")),
    sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    revision_column(),
    created_at(),
    updated_at(),
    # One mutable state row per (user, artifact version): a collaborator's study actions
    # can only touch their own row (ARCH-05-012/013).
    sa.UniqueConstraint(
        "user_id", "artifact_version_id", name="uq_user_artifact_state_user_version"
    ),
)

study_session_snapshots = sa.Table(
    "study_session_snapshots",
    METADATA,
    uuid_pk(),
    # Immutable, user-private materialization of state + exact artifact version (ARCH-05-014).
    uuid_fk("user_id", "users", ondelete="CASCADE"),
    uuid_fk("artifact_version_id", "artifact_versions", ondelete="RESTRICT"),
    uuid_fk("source_state_id", "user_artifact_state", ondelete="RESTRICT"),
    sa.Column(
        "visibility",
        sa.Text,
        nullable=False,
        server_default=sa.text("'private'"),
    ),
    # Only the progress/answers/results needed for the request (frozen at creation).
    sa.Column("snapshot", JSONB, nullable=False),
    created_at(),
    sa.CheckConstraint("visibility = 'private'", name="ck_study_session_snapshots_private"),
)
