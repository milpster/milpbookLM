"""Identity tables: users, sessions (ch05 "users/sessions")."""

from __future__ import annotations

import sqlalchemy as sa

from ._common import (
    METADATA,
    created_at,
    etag_column,
    revision_column,
    updated_at,
    uuid_fk,
    uuid_pk,
)

users = sa.Table(
    "users",
    METADATA,
    uuid_pk(),
    sa.Column("email", sa.Text, nullable=False, unique=True),
    sa.Column("display_name", sa.Text, nullable=False),
    sa.Column("password_hash", sa.Text, nullable=False),
    sa.Column(
        "status",
        sa.Text,
        nullable=False,
        server_default=sa.text("'active'"),
    ),
    revision_column(),
    etag_column(),
    created_at(),
    updated_at(),
    sa.CheckConstraint("status IN ('active', 'disabled', 'deleted')", name="ck_users_status"),
)

sessions = sa.Table(
    "sessions",
    METADATA,
    uuid_pk(),
    uuid_fk("user_id", "users", ondelete="CASCADE"),
    # Session tokens are 256-bit CSPRNG opaque tokens; only a keyed hash is stored.
    sa.Column("token_hash", sa.Text, nullable=False, unique=True),
    sa.Column("user_agent", sa.Text, nullable=True),
    sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("expires_at > created_at", name="ck_sessions_expiry"),
)
