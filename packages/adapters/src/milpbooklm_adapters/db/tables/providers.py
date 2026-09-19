"""
Provider and connector tables (ch05 provider/connector configs and credentials).

Credentials are encrypted at rest (libsodium XChaCha20-Poly1305, per-record nonce,
versioned key ID) - only ciphertext crosses the trust boundary. Provider != Model and
Model != ModelRole: configs name a provider kind, never a specific model (architecture ch05 §11).
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

provider_configs = sa.Table(
    "provider_configs",
    METADATA,
    uuid_pk(),
    sa.Column("provider_kind", sa.Text, nullable=False),
    sa.Column("display_name", sa.Text, nullable=False),
    sa.Column("base_url", sa.Text, nullable=True),
    sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
    revision_column(),
    etag_column(),
    created_at(),
    updated_at(),
    sa.UniqueConstraint("provider_kind", "display_name", name="uq_provider_configs_kind_name"),
)

provider_credentials = sa.Table(
    "provider_credentials",
    METADATA,
    uuid_pk(),
    uuid_fk("provider_config_id", "provider_configs", ondelete="CASCADE"),
    # NULL owner = installation-level credential; a set user = personal credential.
    uuid_fk("owner_user_id", "users", nullable=True, ondelete="CASCADE"),
    sa.Column("credential_kind", sa.Text, nullable=False),
    sa.Column("encrypted_payload", sa.LargeBinary, nullable=False),
    sa.Column("key_id", sa.Text, nullable=False),
    sa.Column("nonce", sa.LargeBinary, nullable=False),
    created_at(),
    updated_at(),
    sa.Index(
        "uq_provider_credentials_config_owner",
        "provider_config_id",
        "owner_user_id",
        unique=True,
        postgresql_nulls_not_distinct=True,
    ),
)

connector_configs = sa.Table(
    "connector_configs",
    METADATA,
    uuid_pk(),
    sa.Column("connector_kind", sa.Text, nullable=False),
    sa.Column("display_name", sa.Text, nullable=False),
    sa.Column("endpoint_config", JSONB, nullable=True),
    sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
    revision_column(),
    etag_column(),
    created_at(),
    updated_at(),
    sa.UniqueConstraint("connector_kind", "display_name", name="uq_connector_configs_kind_name"),
)

connector_credentials = sa.Table(
    "connector_credentials",
    METADATA,
    uuid_pk(),
    uuid_fk("connector_config_id", "connector_configs", ondelete="CASCADE"),
    uuid_fk("owner_user_id", "users", nullable=True, ondelete="CASCADE"),
    sa.Column("encrypted_payload", sa.LargeBinary, nullable=False),
    sa.Column("key_id", sa.Text, nullable=False),
    sa.Column("nonce", sa.LargeBinary, nullable=False),
    created_at(),
    updated_at(),
    sa.Index(
        "uq_connector_credentials_config_owner",
        "connector_config_id",
        "owner_user_id",
        unique=True,
        postgresql_nulls_not_distinct=True,
    ),
)
