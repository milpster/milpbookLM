"""PostgreSQL manifest freezing, citation validation, and publication."""

from __future__ import annotations

import uuid
from typing import Final

import sqlalchemy as sa
from milpbooklm_application.grounding import (
    AnswerDraft,
    Evidence,
    FrozenManifest,
    GroundedAnswer,
    GroundingError,
    GroundingRequest,
    NoteContext,
)
from milpbooklm_application.note_core import note_content_text
from milpbooklm_contracts.canonical_document import BBOX_COORDINATE_COUNT

from milpbooklm_adapters.db.tables.collaboration import notebook_memberships
from milpbooklm_adapters.db.tables.conversation import messages
from milpbooklm_adapters.db.tables.manifests import (
    generation_input_manifests,
    generation_manifest_items,
)
from milpbooklm_adapters.db.tables.sources import (
    canonical_documents,
    canonical_locators,
    canonical_nodes,
    source_restrictions,
    source_versions,
    sources,
)
from milpbooklm_adapters.db.tables.studio import note_revisions, notes

_PURGED_AVAILABILITY: Final = "deleted_tombstoned"


class PgGroundingStore:
    """The task-16 transaction boundary for immutable grounded answers."""

    def __init__(self, engine: sa.engine.Engine) -> None:
        """Bind the application-role engine."""
        self._engine = engine

    def freeze(self, *, request: GroundingRequest, normalized_question: str) -> FrozenManifest:
        """Record the authorization-filtered source and explicit-note scope."""
        with self._engine.begin() as connection:
            source_version_ids = self._selected_versions(connection, request)
            note_contexts = self._selected_note_contexts(connection, request)
            manifest_id = uuid.uuid4()
            _ = connection.execute(
                sa.insert(generation_input_manifests).values(
                    id=manifest_id,
                    notebook_id=request.notebook_id,
                    created_by_user_id=request.actor_user_id,
                    op_kind="ordinary_chat",
                    config_snapshot={
                        "source_only": not note_contexts,
                        "question": normalized_question,
                        "chat": request.chat_config_snapshot or {},
                        "instructions": request.instructions_snapshot,
                        "selected_note_revision_ids": [
                            str(context.revision_id) for context in note_contexts
                        ],
                    },
                    context_snapshot=[str(value) for value in request.context_message_ids],
                    retrieval_version="grounding-v1",
                    retrieval_settings={"reranker": "absent"},
                )
            )
            self._insert_manifest_items(
                connection, manifest_id, source_version_ids, note_contexts
            )
        return FrozenManifest(manifest_id, frozenset(source_version_ids), note_contexts)

    def publish(
        self,
        *,
        request: GroundingRequest,
        manifest: FrozenManifest,
        evidence: tuple[Evidence, ...],
        draft: AnswerDraft,
        retrieval_trace: str,
    ) -> GroundedAnswer:
        """Validate and atomically add an answer message plus server-resolved citations."""
        with self._engine.begin() as connection:
            self._validate(connection, request, manifest, evidence, draft)
            message_id = uuid.uuid4()
            _ = connection.execute(
                sa.insert(messages).values(
                    id=message_id,
                    conversation_id=request.conversation_id,
                    sender_user_id=None,
                    role="assistant",
                    content="".join(span.text for span in draft.spans),
                    manifest_id=manifest.id,
                    selected_source_refs=[str(item.source_version_id) for item in evidence],
                    selected_note_refs=[
                        str(context.revision_id) for context in manifest.note_contexts
                    ],
                    model_metadata={"retrieval_trace": retrieval_trace},
                    provider_status="local",
                    citations=self._citation_payload(
                        connection, evidence, manifest.note_contexts, draft
                    ),
                )
            )
        return GroundedAnswer(message_id, manifest.id, draft.spans, evidence, False)

    def abstain(
        self,
        *,
        request: GroundingRequest,
        manifest: FrozenManifest,
        retrieval_trace: str,
        content: str,
    ) -> GroundedAnswer:
        """Persist a useful limitation as uncited assistant prose."""
        message_id = uuid.uuid4()
        with self._engine.begin() as connection:
            _ = connection.execute(
                sa.insert(messages).values(
                    id=message_id,
                    conversation_id=request.conversation_id,
                    sender_user_id=None,
                    role="assistant",
                    content=content,
                    manifest_id=manifest.id,
                    selected_source_refs=[],
                    selected_note_refs=[],
                    model_metadata={"retrieval_trace": retrieval_trace},
                    provider_status="local",
                    citations=[],
                )
            )
        return GroundedAnswer(message_id, manifest.id, (), (), True)

    def jump(
        self,
        *,
        actor_user_id: uuid.UUID,
        source_version_id: uuid.UUID,
        canonical_node_id: uuid.UUID,
    ) -> dict[str, str | int | tuple[float, ...]]:
        """Resolve a historical version under current authorization or report purge state."""
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(
                        sources.c.availability,
                        sources.c.notebook_id,
                        canonical_documents.c.id.label("canonical_document_id"),
                        canonical_documents.c.contract_json,
                        canonical_nodes.c.parent_node_id,
                        canonical_nodes.c.text_content,
                        canonical_locators.c.locator_kind,
                        canonical_locators.c.page,
                        canonical_locators.c.char_start,
                        canonical_locators.c.char_end,
                        canonical_locators.c.time_ms_start,
                        canonical_locators.c.time_ms_end,
                        canonical_locators.c.bbox,
                    )
                    .join(source_versions, source_versions.c.source_id == sources.c.id)
                    .join(
                        canonical_documents,
                        canonical_documents.c.source_version_id == source_versions.c.id,
                    )
                    .join(
                        canonical_nodes,
                        canonical_nodes.c.canonical_document_id == canonical_documents.c.id,
                    )
                    .join(
                        canonical_locators,
                        canonical_locators.c.canonical_node_id == canonical_nodes.c.id,
                    )
                    .where(
                        source_versions.c.id == source_version_id,
                        canonical_nodes.c.id == canonical_node_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None or row["availability"] == _PURGED_AVAILABILITY:
                return {"state": "unavailable (purged)"}
            if not self._can_read(connection, actor_user_id, source_version_id, row["notebook_id"]):
                raise GroundingError("citation is no longer authorized")
            text_content = row["text_content"]
            if row["parent_node_id"] is None:
                text_content = "\n\n".join(
                    text
                    for text in connection.scalars(
                        sa.select(canonical_nodes.c.text_content)
                        .where(
                            canonical_nodes.c.canonical_document_id
                            == row["canonical_document_id"],
                            canonical_nodes.c.text_content.is_not(None),
                        )
                        .order_by(canonical_nodes.c.seq)
                    )
                    if isinstance(text, str) and text != ""
                )
        payload: dict[str, str | int | tuple[float, ...]] = {
            "state": "available",
            "source_version_id": str(source_version_id),
            "node_id": str(canonical_node_id),
            "locator_kind": row["locator_kind"],
        }
        contract = row["contract_json"]
        media_type = contract.get("mime_type")
        if isinstance(media_type, str):
            payload["media_type"] = media_type
        if isinstance(text_content, str) and text_content != "":
            payload["text"] = text_content
        for field in ("page", "char_start", "char_end", "time_ms_start", "time_ms_end"):
            value = row[field]
            if isinstance(value, int):
                payload[field] = value
        bbox = row["bbox"]
        if isinstance(bbox, list) and len(bbox) == BBOX_COORDINATE_COUNT:
            payload["bbox"] = tuple(value for value in bbox if isinstance(value, (int, float)))
        return payload

    def _selected_versions(
        self, connection: sa.engine.Connection, request: GroundingRequest
    ) -> tuple[uuid.UUID, ...]:
        """Select active readable versions that become the immutable retrieval scope."""
        statement = (
            sa.select(source_versions.c.id)
            .join(sources, sources.c.current_version_id == source_versions.c.id)
            .join(notebook_memberships, notebook_memberships.c.notebook_id == sources.c.notebook_id)
            .where(
                sources.c.notebook_id == request.notebook_id,
                notebook_memberships.c.user_id == request.actor_user_id,
                sources.c.availability.in_(("active", "stale")),
                source_versions.c.status == "active",
                ~sa.exists(
                    sa.select(source_restrictions.c.id).where(
                        source_restrictions.c.source_version_id == source_versions.c.id,
                        source_restrictions.c.restriction_type == "access_denied",
                        sa.or_(
                            source_restrictions.c.user_id.is_(None),
                            source_restrictions.c.user_id == request.actor_user_id,
                        ),
                    )
                ),
            )
            .order_by(source_versions.c.id)
        )
        if request.selected_source_ids is not None:
            statement = statement.where(sources.c.id.in_(request.selected_source_ids))
        return tuple(connection.execute(statement).scalars())

    @staticmethod
    def _selected_note_contexts(
        connection: sa.engine.Connection, request: GroundingRequest
    ) -> tuple[NoteContext, ...]:
        """Resolve only explicit revisions that remain readable in this notebook."""
        selected_ids = request.selected_note_revision_ids
        if not selected_ids:
            return ()
        if len(set(selected_ids)) != len(selected_ids):
            raise GroundingError("selected note revisions must be unique")
        rows = connection.execute(
            sa.select(
                note_revisions.c.id.label("revision_id"),
                note_revisions.c.content,
                notes.c.id.label("note_id"),
                notes.c.title,
            )
            .join(notes, notes.c.id == note_revisions.c.note_id)
            .join(
                notebook_memberships,
                notebook_memberships.c.notebook_id == notes.c.notebook_id,
            )
            .where(
                note_revisions.c.id.in_(selected_ids),
                notes.c.notebook_id == request.notebook_id,
                notebook_memberships.c.user_id == request.actor_user_id,
            )
        ).mappings()
        rows_by_id = {row["revision_id"]: row for row in rows}
        if set(rows_by_id) != set(selected_ids):
            raise GroundingError("one or more selected note revisions are unavailable")
        return tuple(
            NoteContext(
                id=f"n{index}",
                note_id=rows_by_id[revision_id]["note_id"],
                revision_id=revision_id,
                title=rows_by_id[revision_id]["title"],
                text=note_content_text(rows_by_id[revision_id]["content"]),
            )
            for index, revision_id in enumerate(selected_ids, start=1)
        )

    @staticmethod
    def _insert_manifest_items(
        connection: sa.engine.Connection,
        manifest_id: uuid.UUID,
        source_version_ids: tuple[uuid.UUID, ...],
        note_contexts: tuple[NoteContext, ...],
    ) -> None:
        """Attach every selected immutable source and resolved note revision."""
        for source_version_id in source_version_ids:
            _ = connection.execute(
                sa.insert(generation_manifest_items).values(
                    id=uuid.uuid4(),
                    manifest_id=manifest_id,
                    item_kind="source_version",
                    item_id=source_version_id,
                )
            )
        for context in note_contexts:
            _ = connection.execute(
                sa.insert(generation_manifest_items).values(
                    id=uuid.uuid4(),
                    manifest_id=manifest_id,
                    item_kind="note_revision",
                    item_id=context.revision_id,
                )
            )

    def _validate(
        self,
        connection: sa.engine.Connection,
        request: GroundingRequest,
        manifest: FrozenManifest,
        evidence: tuple[Evidence, ...],
        draft: AnswerDraft,
    ) -> None:
        """Recheck source and explicit-note authorization before publication."""
        if self._selected_note_contexts(connection, request) != manifest.note_contexts:
            raise GroundingError("note context is no longer authorized")
        evidence_by_id = {item.id: item for item in evidence}
        note_context_by_id = {item.id: item for item in manifest.note_contexts}
        for span in draft.spans:
            if not span.text.strip() or not span.evidence_ids:
                raise GroundingError("every factual span needs cited evidence")
            for evidence_id in span.evidence_ids:
                item = evidence_by_id.get(evidence_id)
                if item is not None:
                    if item.source_version_id not in manifest.source_version_ids:
                        raise GroundingError("evidence is outside the frozen manifest")
                    self._validate_item(connection, request, item)
                elif evidence_id not in note_context_by_id:
                    raise GroundingError("unsupported evidence id")

    def _validate_item(
        self, connection: sa.engine.Connection, request: GroundingRequest, item: Evidence
    ) -> None:
        """Verify that the supplied immutable evidence coordinates still describe one node."""
        exists = connection.execute(
            sa.select(canonical_nodes.c.id, sources.c.availability)
            .join(
                canonical_documents,
                canonical_documents.c.id == canonical_nodes.c.canonical_document_id,
            )
            .join(source_versions, source_versions.c.id == canonical_documents.c.source_version_id)
            .join(sources, sources.c.id == source_versions.c.source_id)
            .where(
                canonical_nodes.c.id == item.canonical_node_id,
                source_versions.c.id == item.source_version_id,
                sources.c.id == item.source_id,
                sources.c.notebook_id == request.notebook_id,
            )
        ).first()
        if exists is None or exists.availability == _PURGED_AVAILABILITY:
            raise GroundingError("evidence does not exist in the frozen notebook")
        locator = connection.execute(
            sa.select(canonical_locators.c.id).where(
                canonical_locators.c.canonical_node_id == item.canonical_node_id,
                sa.or_(
                    # Char-typed locators must cover the cited span.
                    sa.and_(
                        canonical_locators.c.char_start <= item.char_start,
                        canonical_locators.c.char_end >= item.char_end,
                    ),
                    # Structural locators (block/slide/sheet/bbox) carry no
                    # char extents; chunk spans are node-relative by chunker
                    # construction, so identity + authorization above apply.
                    sa.and_(
                        canonical_locators.c.char_start.is_(None),
                        canonical_locators.c.char_end.is_(None),
                    ),
                ),
            )
        ).first()
        if locator is None:
            raise GroundingError("evidence has no valid canonical locator")
        if not self._can_read(
            connection, request.actor_user_id, item.source_version_id, request.notebook_id
        ):
            raise GroundingError("evidence is no longer authorized")

    @staticmethod
    def _can_read(
        connection: sa.engine.Connection,
        actor_user_id: uuid.UUID,
        source_version_id: uuid.UUID,
        notebook_id: uuid.UUID,
    ) -> bool:
        """Recheck current membership and restrictions at publication/jump time."""
        return (
            connection.execute(
                sa.select(notebook_memberships.c.notebook_id).where(
                    notebook_memberships.c.notebook_id == notebook_id,
                    notebook_memberships.c.user_id == actor_user_id,
                    ~sa.exists(
                        sa.select(source_restrictions.c.id).where(
                            source_restrictions.c.source_version_id == source_version_id,
                            source_restrictions.c.restriction_type == "access_denied",
                            sa.or_(
                                source_restrictions.c.user_id.is_(None),
                                source_restrictions.c.user_id == actor_user_id,
                            ),
                        )
                    ),
                )
            ).first()
            is not None
        )

    @staticmethod
    def _citation_payload(
        connection: sa.engine.Connection,
        evidence: tuple[Evidence, ...],
        note_contexts: tuple[NoteContext, ...],
        draft: AnswerDraft,
    ) -> list[dict[str, str | int]]:
        """Resolve source locators and exact note-revision links after validation."""
        evidence_by_id = {item.id: item for item in evidence}
        note_by_id = {item.id: item for item in note_contexts}
        payload: list[dict[str, str | int]] = []
        for span in draft.spans:
            for evidence_id in span.evidence_ids:
                item = evidence_by_id.get(evidence_id)
                if item is None:
                    note = note_by_id[evidence_id]
                    payload.append(
                        {
                            "evidence_id": note.id,
                            "label": note.title,
                            "note_id": str(note.note_id),
                            "note_revision_id": str(note.revision_id),
                            "locator_kind": "note_revision",
                            "url": f"/api/v1/note-revisions/{note.revision_id}",
                        }
                    )
                    continue
                locator = (
                    connection.execute(
                        sa.select(
                            canonical_locators.c.locator_kind,
                            canonical_locators.c.page,
                            canonical_locators.c.char_start,
                            canonical_locators.c.char_end,
                        )
                        .where(canonical_locators.c.canonical_node_id == item.canonical_node_id)
                        .limit(1)
                    )
                    .mappings()
                    .one()
                )
                payload.append(
                    {
                        "evidence_id": item.id,
                        "label": item.label,
                        "source_version_id": str(item.source_version_id),
                        "node_id": str(item.canonical_node_id),
                        "locator_kind": locator["locator_kind"],
                        "char_start": item.char_start,
                        "char_end": item.char_end,
                        "url": (
                            f"/api/v1/source-versions/{item.source_version_id}"
                            f"/nodes/{item.canonical_node_id}"
                        ),
                    }
                )
        return payload
