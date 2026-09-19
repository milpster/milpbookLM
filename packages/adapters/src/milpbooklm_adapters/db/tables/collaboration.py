"""Collaboration tables: notebooks, memberships, share links, notifications."""

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

notebooks = sa.Table(
    "notebooks",
    METADATA,
    uuid_pk(),
    sa.Column("title", sa.Text, nullable=False),
    sa.Column("description", sa.Text, nullable=True),
    # Notebook-wide custom instructions, as actually applied at generation time (ARCH-05-015).
    sa.Column("instructions", sa.Text, nullable=True),
    sa.Column(
        "default_selected_source_behavior",
        sa.Text,
        nullable=False,
        server_default=sa.text("'all_sources'"),
    ),
    sa.Column("source_organization", JSONB, nullable=True),
    sa.Column("model_role_overrides", JSONB, nullable=True),
    sa.Column(
        "sharing_state",
        sa.Text,
        nullable=False,
        server_default=sa.text("'private'"),
    ),
    # ch05 mandatory invariant: every notebook has at least one owner membership OR an
    # explicit locked administrative-custody state. The "at least one" half is enforced by
    # the final-owner serializable section (FND-03 3.4.1), not by a single-row constraint.
    sa.Column(
        "custody_state",
        sa.Text,
        nullable=False,
        server_default=sa.text("'none'"),
    ),
    # ARCH-05-002: an optional denormalized owner pointer is stored for display only and
    # MUST NOT be the authorization source of truth (ownership.py enforces membership truth).
    uuid_fk("owner_user_id", "users", nullable=True, ondelete="SET NULL"),
    uuid_fk("created_by_user_id", "users"),
    revision_column(),
    etag_column(),
    created_at(),
    updated_at(),
    sa.CheckConstraint(
        "custody_state IN ('none', 'locked_admin_custody')",
        name="ck_notebooks_custody_state",
    ),
    sa.CheckConstraint(
        "sharing_state IN ('private', 'shared', 'public')",
        name="ck_notebooks_sharing_state",
    ),
    sa.CheckConstraint(
        "default_selected_source_behavior IN ('all_sources', 'none')",
        name="ck_notebooks_selected_source_behavior",
    ),
)

notebook_memberships = sa.Table(
    "notebook_memberships",
    METADATA,
    uuid_pk(),
    uuid_fk("notebook_id", "notebooks", ondelete="CASCADE"),
    uuid_fk("user_id", "users", ondelete="CASCADE"),
    sa.Column(
        "role",
        sa.Text,
        nullable=False,
    ),
    uuid_fk("granted_by_user_id", "users", nullable=True, ondelete="SET NULL"),
    created_at(),
    updated_at(),
    sa.UniqueConstraint("notebook_id", "user_id", name="uq_notebook_memberships_notebook_user"),
    sa.CheckConstraint(
        "role IN ('owner', 'editor', 'viewer')",
        name="ck_notebook_memberships_role",
    ),
)

share_links = sa.Table(
    "share_links",
    METADATA,
    uuid_pk(),
    uuid_fk("notebook_id", "notebooks", ondelete="CASCADE"),
    uuid_fk("artifact_version_id", "artifact_versions", nullable=True, ondelete="CASCADE"),
    sa.Column("token_hash", sa.Text, nullable=False, unique=True),
    sa.Column(
        "visibility",
        sa.Text,
        nullable=False,
        server_default=sa.text("'private'"),
    ),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    uuid_fk("created_by_user_id", "users"),
    created_at(),
    # Partial unique: at most ONE live share link per artifact (ch05 "partial unique indexes").
    sa.Index(
        "uq_share_links_one_live_per_artifact",
        "notebook_id",
        "artifact_version_id",
        unique=True,
        postgresql_where=sa.text("artifact_version_id IS NOT NULL AND revoked_at IS NULL"),
    ),
    sa.CheckConstraint("visibility IN ('private', 'public')", name="ck_share_links_visibility"),
)

notifications = sa.Table(
    "notifications",
    METADATA,
    uuid_pk(),
    uuid_fk("user_id", "users", ondelete="CASCADE"),
    sa.Column("kind", sa.Text, nullable=False),
    sa.Column("payload", JSONB, nullable=True),
    sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    created_at(),
    sa.CheckConstraint(
        "read_at IS NULL OR read_at >= created_at",
        name="ck_notifications_read_after_create",
    ),
)
