"""PostgreSQL persistence for immutable canonical parser results."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from milpbooklm_contracts.canonical_document import CanonicalDocument, CanonicalNode

from milpbooklm_adapters.db.tables.sources import (
    canonical_documents,
    canonical_locators,
    canonical_nodes,
    source_versions,
)


class PgCanonicalRepository:
    """Persist one deterministic canonical representation per parser profile."""

    def __init__(self, engine: sa.engine.Engine) -> None:
        """Bind the application-role engine."""
        self._engine = engine

    def mark_parsing(self, source_version_id: uuid.UUID) -> None:
        """Expose that parser work has begun without claiming activation."""
        with self._engine.begin() as connection:
            connection.execute(
                sa.update(source_versions)
                .where(source_versions.c.id == source_version_id)
                .values(status="parsing", parse_error_code=None)
            )

    def persist(self, document: CanonicalDocument) -> None:
        """Atomically store validated JSON, normalized nodes/locators, and parsed state."""
        with self._engine.begin() as connection:
            connection.execute(
                sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"),
                {"identity": f"canonical:{document.document_id}"},
            )
            exists = connection.execute(
                sa.select(canonical_documents.c.id).where(
                    canonical_documents.c.id == document.document_id
                )
            ).first()
            if exists is None:
                self._insert_document(connection, document)
            connection.execute(
                sa.update(source_versions)
                .where(source_versions.c.id == document.source_version_id)
                .values(status="parsed", parse_error_code=None)
            )

    def persist_failure(self, source_version_id: uuid.UUID, error_code: str) -> None:
        """Store an explicit terminal parse outcome without creating a document."""
        status = "encrypted" if error_code == "encrypted" else "parse_failed"
        with self._engine.begin() as connection:
            connection.execute(
                sa.update(source_versions)
                .where(source_versions.c.id == source_version_id)
                .values(status=status, parse_error_code=error_code)
            )

    @staticmethod
    def _insert_document(
        connection: sa.engine.Connection, document: CanonicalDocument
    ) -> None:
        connection.execute(
            sa.insert(canonical_documents).values(
                id=document.document_id,
                source_version_id=document.source_version_id,
                canonical_schema_version=document.schema_version,
                parser_identity=document.parser.identity,
                parser_version=document.parser.version,
                parser_profile=document.parser.profile,
                tool_versions=list(document.parser.tool_versions),
                contract_json=document.to_json(),
                active=False,
            )
        )
        inserted: set[uuid.UUID] = set()
        for sequence, node in enumerate(document.nodes):
            if node.parent_id is not None and node.parent_id not in inserted:
                raise CanonicalPersistenceError("node parent must precede its child")
            PgCanonicalRepository._insert_node(connection, document.document_id, node, sequence)
            inserted.add(node.node_id)

    @staticmethod
    def _insert_node(
        connection: sa.engine.Connection,
        document_id: uuid.UUID,
        node: CanonicalNode,
        sequence: int,
    ) -> None:
        connection.execute(
            sa.insert(canonical_nodes).values(
                id=node.node_id,
                canonical_document_id=document_id,
                parent_node_id=node.parent_id,
                node_type=node.kind.value,
                heading_level=1 if node.kind.value == "heading" else None,
                seq=sequence,
                text_content=node.text,
                structural_identity=node.structural_identity,
                authority_class=node.authority.value,
                language=node.language,
            )
        )
        locator = node.locator
        locator_kind = (
            "bbox" if locator.bbox is not None else "page" if locator.page else "char_range"
        )
        connection.execute(
            sa.insert(canonical_locators).values(
                id=uuid.uuid5(node.node_id, "locator:primary"),
                canonical_node_id=node.node_id,
                locator_kind=locator_kind,
                page=locator.page,
                char_start=locator.char_start,
                char_end=locator.char_end,
                bbox=list(locator.bbox) if locator.bbox is not None else None,
                structural_path=list(locator.path),
            )
        )


class CanonicalPersistenceError(RuntimeError):
    """The canonical tree cannot be persisted without violating its parent order."""
