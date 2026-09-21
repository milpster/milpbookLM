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
)

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

_PURGED_AVAILABILITY: Final = "deleted_tombstoned"


class PgGroundingStore:
    """The task-16 transaction boundary for immutable grounded answers."""

    def __init__(self, engine: sa.engine.Engine) -> None:
        """Bind the application-role engine."""
        self._engine = engine

    def freeze(self, *, request: GroundingRequest, normalized_question: str) -> FrozenManifest:
        """Record the authorization-filtered version scope before retrieval begins."""
        with self._engine.begin() as connection:
            source_version_ids = self._selected_versions(connection, request)
            manifest_id = uuid.uuid4()
            _ = connection.execute(
                sa.insert(generation_input_manifests).values(
                    id=manifest_id,
                    notebook_id=request.notebook_id,
                    created_by_user_id=request.actor_user_id,
                    op_kind="ordinary_chat",
                    config_snapshot={"source_only": True, "question": normalized_question},
                    context_snapshot=[str(value) for value in request.context_message_ids],
                    retrieval_version="grounding-v1",
                    retrieval_settings={"reranker": "absent"},
                )
            )
            self._insert_manifest_items(connection, manifest_id, source_version_ids, request)
        return FrozenManifest(manifest_id, frozenset(source_version_ids))

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
                    selected_note_refs=[str(item) for item in request.selected_note_revision_ids],
                    model_metadata={"retrieval_trace": retrieval_trace},
                    provider_status="local",
                    citations=self._citation_payload(connection, evidence, draft),
                )
            )
        return GroundedAnswer(message_id, manifest.id, draft.spans, evidence, False)

    def abstain(self, *, manifest: FrozenManifest, retrieval_trace: str) -> GroundedAnswer:
        """Return source-only insufficiency without an assistant-message row."""
        del retrieval_trace
        return GroundedAnswer(None, manifest.id, (), (), True)

    def jump(
        self,
        *,
        actor_user_id: uuid.UUID,
        source_version_id: uuid.UUID,
        canonical_node_id: uuid.UUID,
    ) -> dict[str, str]:
        """Resolve a historical version under current authorization or report purge state."""
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(sources.c.availability, sources.c.notebook_id)
                    .join(source_versions, source_versions.c.source_id == sources.c.id)
                    .join(
                        canonical_documents,
                        canonical_documents.c.source_version_id == source_versions.c.id,
                    )
                    .join(
                        canonical_nodes,
                        canonical_nodes.c.canonical_document_id == canonical_documents.c.id,
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
        return {
            "state": "available",
            "source_version_id": str(source_version_id),
            "node_id": str(canonical_node_id),
        }

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
    def _insert_manifest_items(
        connection: sa.engine.Connection,
        manifest_id: uuid.UUID,
        source_version_ids: tuple[uuid.UUID, ...],
        request: GroundingRequest,
    ) -> None:
        """Attach every selected immutable source and note revision to the manifest."""
        for source_version_id in source_version_ids:
            _ = connection.execute(
                sa.insert(generation_manifest_items).values(
                    id=uuid.uuid4(),
                    manifest_id=manifest_id,
                    item_kind="source_version",
                    item_id=source_version_id,
                )
            )
        for note_revision_id in request.selected_note_revision_ids:
            _ = connection.execute(
                sa.insert(generation_manifest_items).values(
                    id=uuid.uuid4(),
                    manifest_id=manifest_id,
                    item_kind="note_revision",
                    item_id=note_revision_id,
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
        """Enforce evidence existence, manifest membership, authz, locator, and claim links."""
        by_id = {item.id: item for item in evidence}
        for span in draft.spans:
            if not span.text.strip() or not span.evidence_ids:
                raise GroundingError("every factual span needs cited evidence")
            for evidence_id in span.evidence_ids:
                item = by_id.get(evidence_id)
                if item is None:
                    raise GroundingError("unsupported evidence id")
                if item.source_version_id not in manifest.source_version_ids:
                    raise GroundingError("evidence is outside the frozen manifest")
                self._validate_item(connection, request, item)

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
                canonical_locators.c.char_start <= item.char_start,
                canonical_locators.c.char_end >= item.char_end,
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
        connection: sa.engine.Connection, evidence: tuple[Evidence, ...], draft: AnswerDraft
    ) -> list[dict[str, str | int]]:
        """Resolve labels and locators server-side after every citation is validated."""
        evidence_by_id = {item.id: item for item in evidence}
        payload: list[dict[str, str | int]] = []
        for span in draft.spans:
            for evidence_id in span.evidence_ids:
                item = evidence_by_id[evidence_id]
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
