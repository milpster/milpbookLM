"""
Transactional source activation (ING-01c, ch05 active-version invariants).

Activation is a single database transaction after the required artifacts exist:
the parsed source version and its canonical document. The old active version is
demoted BEFORE the parsed one is promoted, so the partial unique index on
active versions never sees two active versions of one source (empirically
verified: the promote-first order is rejected by uq_source_versions_one_active
inside the same transaction). A missing artifact or a lost compare-and-swap
exits without mutations, so the prior active version stays intact (refresh-
failure retention). Concurrent activations serialize on the source-row lock;
the partial unique index makes a double win impossible.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from milpbooklm_application.source_acquisition import SourceNotFoundError
from sqlalchemy.engine import Connection, RowMapping

from milpbooklm_adapters.db.tables.collaboration import notebook_memberships
from milpbooklm_adapters.db.tables.sources import (
    canonical_documents,
    source_versions,
    sources,
)

from .pg_provenance import insert_activation_edges


class SourceActivationStore:
    """The atomic parsed→active swap for one source."""

    def __init__(self, engine: sa.engine.Engine) -> None:
        """Bind the application-role engine."""
        self._engine = engine

    def activate(self, source_id: uuid.UUID, actor_id: uuid.UUID) -> bool:
        """Promote the parsed version with its canonical document atomically."""
        with self._engine.begin() as connection:
            source = self._locked_source(connection, source_id, actor_id)
            if source is None:
                raise SourceNotFoundError
            version = self._locked_latest_version(connection, source_id)
            if version is None or version["status"] != "parsed":
                return False
            document = self._locked_document(connection, version["id"])
            if document is None:
                return False
            self._demote_prior_active(connection, source_id, version["id"])
            promoted = self._promote(connection, version["id"])
            if not promoted:
                return False
            self._activate_document(connection, version["id"], document["id"])
            insert_activation_edges(connection, source_id, version, document)
            connection.execute(
                sa.update(sources)
                .where(sources.c.id == source_id)
                .values(
                    current_version_id=version["id"],
                    availability="active",
                    revision=sources.c.revision + 1,
                    etag=sa.cast(sources.c.revision + 1, sa.Text),
                    updated_at=sa.func.now(),
                )
            )
        return True

    @staticmethod
    def _locked_source(
        connection: Connection, source_id: uuid.UUID, actor_id: uuid.UUID
    ) -> RowMapping | None:
        """Membership-scoped source row locked for the activation transaction."""
        return connection.execute(
            sa.select(sources.c.id)
            .where(
                sources.c.id == source_id,
                sources.c.notebook_id.in_(
                    sa.select(notebook_memberships.c.notebook_id).where(
                        notebook_memberships.c.user_id == actor_id
                    )
                ),
            )
            .with_for_update()
        ).mappings().first()

    @staticmethod
    def _locked_latest_version(
        connection: Connection, source_id: uuid.UUID
    ) -> RowMapping | None:
        """Return the newest version row (id, status, blob) locked for the swap."""
        return connection.execute(
            sa.select(
                source_versions.c.id,
                source_versions.c.status,
                source_versions.c.original_blob_id,
            )
            .where(source_versions.c.source_id == source_id)
            .order_by(source_versions.c.version_number.desc())
            .limit(1)
            .with_for_update()
        ).mappings().first()

    @staticmethod
    def _locked_document(
        connection: Connection, source_version_id: uuid.UUID
    ) -> RowMapping | None:
        """Return the canonical document row (id, parser identity) locked for the swap."""
        return connection.execute(
            sa.select(
                canonical_documents.c.id,
                canonical_documents.c.parser_identity,
                canonical_documents.c.parser_version,
            )
            .where(canonical_documents.c.source_version_id == source_version_id)
            .with_for_update()
        ).mappings().first()

    @staticmethod
    def _demote_prior_active(
        connection: Connection, source_id: uuid.UUID, promoted_id: uuid.UUID
    ) -> None:
        """Retire the prior active version before the promotion (unique-index safe)."""
        connection.execute(
            sa.update(source_versions)
            .where(
                source_versions.c.source_id == source_id,
                source_versions.c.status == "active",
                source_versions.c.id != promoted_id,
            )
            .values(status="inactive")
        )

    @staticmethod
    def _promote(connection: Connection, version_id: uuid.UUID) -> bool:
        """CAS-promote the parsed version; a lost swap means no activation."""
        result = connection.execute(
            sa.update(source_versions)
            .where(
                source_versions.c.id == version_id,
                source_versions.c.status == "parsed",
            )
            .values(status="active", activated_at=sa.func.now())
        )
        return result.rowcount == 1

    @staticmethod
    def _activate_document(
        connection: Connection, source_version_id: uuid.UUID, document_id: uuid.UUID
    ) -> None:
        """Atomic active-document swap: demote others, then flip this document."""
        connection.execute(
            sa.update(canonical_documents)
            .where(
                canonical_documents.c.source_version_id == source_version_id,
                canonical_documents.c.active.is_(True),
                canonical_documents.c.id != document_id,
            )
            .values(active=False)
        )
        connection.execute(
            sa.update(canonical_documents)
            .where(canonical_documents.c.id == document_id)
            .values(active=True, activated_at=sa.func.now())
        )
