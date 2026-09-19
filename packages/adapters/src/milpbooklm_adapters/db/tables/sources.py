"""
Source tables: sources, versions, restrictions, canonical documents/nodes/locators (ch05).

ARCH-05-003/004 invariants expressed in DDL:
* a source carries type, origin, display title, connector metadata, current-version pointer,
  availability state and an optional access/restriction policy;
* a SourceVersion never changes bytes/canonical document/checksum after activation
  (immutability trigger in triggers.py);
* retrieval uses only the atomic active version: at most one active source version and
  at most one active canonical document per source version (partial unique indexes).
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

sources = sa.Table(
    "sources",
    METADATA,
    uuid_pk(),
    uuid_fk("notebook_id", "notebooks", ondelete="CASCADE"),
    sa.Column("type", sa.Text, nullable=False),
    # Upstream identity: unchanged by any metadata edit (ARCH-05-003).
    sa.Column("origin", sa.Text, nullable=False),
    # Local display title is metadata on the logical Source; editing it never rewrites
    # original bytes, upstream identity, SourceVersion content or historical manifests.
    sa.Column("display_title", sa.Text, nullable=False),
    uuid_fk("connector_config_id", "connector_configs", nullable=True, ondelete="SET NULL"),
    uuid_fk("current_version_id", "source_versions", nullable=True, ondelete="SET NULL"),
    sa.Column(
        "availability",
        sa.Text,
        nullable=False,
        server_default=sa.text("'active'"),
        # ch05: at least active, stale/refresh-failed, inaccessible/revoked, deleted/tombstoned.
    ),
    # Optional access/restriction policy (restricted connector sources); per-user checks and
    # reuse/export restrictions live in source_restrictions, never in canonical content.
    sa.Column("restriction_policy", JSONB, nullable=True),
    uuid_fk("created_by_user_id", "users"),
    revision_column(),
    etag_column(),
    created_at(),
    updated_at(),
    sa.CheckConstraint(
        "availability IN ('active', 'stale', 'inaccessible_revoked', 'deleted_tombstoned')",
        name="ck_sources_availability",
    ),
)

source_versions = sa.Table(
    "source_versions",
    METADATA,
    uuid_pk(),
    uuid_fk("source_id", "sources", ondelete="CASCADE"),
    sa.Column("version_number", sa.Integer, nullable=False),
    uuid_fk("original_blob_id", "blob_objects", nullable=True, ondelete="SET NULL"),
    sa.Column("content_sha256", sa.Text, nullable=False),
    sa.Column("content_size_bytes", sa.BigInteger, nullable=True),
    sa.Column(
        "status",
        sa.Text,
        nullable=False,
        server_default=sa.text("'activating'"),
    ),
    sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("tombstoned_at", sa.DateTime(timezone=True), nullable=True),
    uuid_fk("created_by_user_id", "users"),
    created_at(),
    sa.UniqueConstraint("source_id", "version_number", name="uq_source_versions_source_number"),
    # Atomic active version: at most one active version per source (ARCH-05 mandatory invariant
    # "retrieval uses only the atomic active version"); swapped by the active-swap section.
    sa.Index(
        "uq_source_versions_one_active",
        "source_id",
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    ),
    sa.CheckConstraint("version_number > 0", name="ck_source_versions_number"),
    sa.CheckConstraint(
        "status IN ('activating', 'active', 'inactive', 'tombstoned')",
        name="ck_source_versions_status",
    ),
)

source_restrictions = sa.Table(
    "source_restrictions",
    METADATA,
    uuid_pk(),
    uuid_fk("source_version_id", "source_versions", ondelete="CASCADE"),
    # NULL user = restriction applies to every user; a set user = per-user access check.
    uuid_fk("user_id", "users", nullable=True, ondelete="CASCADE"),
    sa.Column(
        "restriction_type",
        sa.Text,
        nullable=False,
    ),
    sa.Column("reason", sa.Text, nullable=True),
    uuid_fk("created_by_user_id", "users"),
    created_at(),
    sa.UniqueConstraint(
        "source_version_id",
        "user_id",
        "restriction_type",
        name="uq_source_restrictions_version_user_type",
        # A NULL user (all-users) restriction must not collide with per-user rows.
        postgresql_nulls_not_distinct=True,
    ),
    sa.CheckConstraint(
        "restriction_type IN ('access_denied', 'export_denied', 'share_denied', 'reuse_denied')",
        name="ck_source_restrictions_type",
    ),
)

canonical_documents = sa.Table(
    "canonical_documents",
    METADATA,
    uuid_pk(),
    uuid_fk("source_version_id", "source_versions", ondelete="CASCADE"),
    # A retained SourceVersion may carry multiple immutable representations over its lifetime;
    # exactly one is active for new retrieval (partial unique below). Fully immutable (trigger).
    sa.Column("canonical_schema_version", sa.Text, nullable=False),
    sa.Column("parser_version", sa.Text, nullable=False),
    sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("false")),
    sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
    created_at(),
    sa.Index(
        "uq_canonical_documents_one_active",
        "source_version_id",
        unique=True,
        postgresql_where=sa.text("active = true"),
    ),
)

canonical_nodes = sa.Table(
    "canonical_nodes",
    METADATA,
    uuid_pk(),
    uuid_fk("canonical_document_id", "canonical_documents", ondelete="CASCADE"),
    # Tree of document structure; parent NULL = root. Fully immutable (trigger).
    uuid_fk("parent_node_id", "canonical_nodes", nullable=True, ondelete="CASCADE"),
    sa.Column(
        "node_type",
        sa.Text,
        nullable=False,
    ),
    sa.Column("heading_level", sa.Integer, nullable=True),
    sa.Column("seq", sa.Integer, nullable=False),
    sa.Column("text_content", sa.Text, nullable=True),
    created_at(),
    sa.UniqueConstraint("canonical_document_id", "seq", name="uq_canonical_nodes_document_seq"),
    sa.CheckConstraint(
        "node_type = 'heading' AND heading_level IS NOT NULL OR node_type <> 'heading'",
        name="ck_canonical_nodes_heading_level",
    ),
    sa.CheckConstraint(
        "node_type IN ('heading', 'paragraph', 'list', 'list_item', 'table', 'image', "
        "'page', 'slide', 'sheet')",
        name="ck_canonical_nodes_type",
    ),
)

canonical_locators = sa.Table(
    "canonical_locators",
    METADATA,
    uuid_pk(),
    uuid_fk("canonical_node_id", "canonical_nodes", ondelete="CASCADE"),
    sa.Column(
        "locator_kind",
        sa.Text,
        nullable=False,
    ),
    sa.Column("page", sa.Integer, nullable=True),
    sa.Column("slide", sa.Integer, nullable=True),
    sa.Column("sheet", sa.Text, nullable=True),
    sa.Column("row_start", sa.Integer, nullable=True),
    sa.Column("row_end", sa.Integer, nullable=True),
    sa.Column("col_start", sa.Integer, nullable=True),
    sa.Column("col_end", sa.Integer, nullable=True),
    sa.Column("char_start", sa.Integer, nullable=True),
    sa.Column("char_end", sa.Integer, nullable=True),
    sa.Column("time_ms_start", sa.BigInteger, nullable=True),
    sa.Column("time_ms_end", sa.BigInteger, nullable=True),
    sa.Column("bbox", JSONB, nullable=True),
    created_at(),
    # One locator of a given kind and extent per node (NULLs must not collide).
    sa.Index(
        "uq_canonical_locators_node_extent",
        "canonical_node_id",
        "locator_kind",
        "char_start",
        "char_end",
        "page",
        "slide",
        unique=True,
        postgresql_nulls_not_distinct=True,
    ),
    sa.CheckConstraint(
        "row_end IS NULL OR row_start IS NULL OR row_end >= row_start",
        name="ck_canonical_locators_row_range",
    ),
    sa.CheckConstraint(
        "char_end IS NULL OR char_start IS NULL OR char_end >= char_start",
        name="ck_canonical_locators_char_range",
    ),
    sa.CheckConstraint(
        "time_ms_end IS NULL OR time_ms_start IS NULL OR time_ms_end >= time_ms_start",
        name="ck_canonical_locators_time_range",
    ),
    sa.CheckConstraint(
        "locator_kind IN ('page', 'bbox', 'slide', 'sheet', 'row_range', "
        "'char_range', 'time_range')",
        name="ck_canonical_locators_kind",
    ),
)
