"""
Constrained retrieval SQL (IDX-01, ch08): the authz-in-query enforcement point.

Authorization lives IN the query, never in Python post-filtering only: the
actor must be a notebook member, the source must be active/stale, and only the
atomic active source version is served. Requested source IDs intersect the
authorized set (injected foreign IDs return zero rows). Lexical ranking is
native PostgreSQL FTS (websearch_to_tsquery per-row config); vector ranking is
cosine distance over the stored embeddings. After hydration, access_denied
restrictions are re-checked (policy can change after a generation was built);
denied rows are dropped and the deny is logged. If the re-check (or an HNSW
index, once enabled) under-returns, the query is retried with a larger
limit - the authorization filters are NEVER relaxed to make up rows.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from milpbooklm_application.retrieval import RetrievalCommand, RetrievedRow
from milpbooklm_domain.indexing import NodeSpan

logger = logging.getLogger(__name__)

_OVERFETCH_CAPS = (100, 200, 500)
_OVERFETCH_FACTORS = (3, 10, 30)

_BASE_SQL = """
FROM index_chunks ic
JOIN index_generations g ON g.id = ic.index_generation_id AND g.status = 'ready'
JOIN sources s ON s.id = ic.source_id
JOIN source_versions sv ON sv.id = ic.source_version_id
WHERE ic.notebook_id = :notebook_id
  AND s.notebook_id IN (
    SELECT nm.notebook_id FROM notebook_memberships nm
    WHERE nm.user_id = :actor_user_id
  )
  AND s.availability IN ('active', 'stale')
  AND (sv.status = 'active' OR :allow_pinned_versions)
"""

_COLUMN_LIST = """
ic.id, ic.notebook_id, ic.source_id, ic.source_version_id, s.display_title,
ic.canonical_node_id, ic.char_start, ic.char_end, ic.text, ic.token_count,
ic.language, ic.section_ancestry, ic.node_spans
"""


class PgRetrievalService:
    """The constrained retrieval SQL behind the application RetrievalPort."""

    def __init__(self, engine: sa.engine.Engine) -> None:
        """Bind the application-role engine."""
        self._engine = engine

    def search(
        self,
        command: RetrievalCommand,
        *,
        retriever: str,
        query_embedding_text: str | None,
    ) -> tuple[RetrievedRow, ...]:
        """Return ranked, hydrated, policy-rechecked rows for one retriever."""
        if retriever == "lexical":
            return self._lexical(command)
        if retriever == "vector":
            if query_embedding_text is None:
                return ()
            return self._vector(command, query_embedding_text)
        raise ValueError(f"unknown retriever: {retriever}")

    def _overfetch_limits(self, top_k: int) -> tuple[int, ...]:
        pairs = zip(_OVERFETCH_CAPS, _OVERFETCH_FACTORS, strict=True)
        return tuple(min(cap, top_k * factor) for cap, factor in pairs)

    def _lexical(self, command: RetrievalCommand) -> tuple[RetrievedRow, ...]:
        sql = (
            f"SELECT {_COLUMN_LIST}, "
            "ts_rank(ic.fts_vector, websearch_to_tsquery(ic.fts_config::regconfig, :query)) "
            "AS raw_score "
            + _BASE_SQL
            + "  AND ic.fts_vector @@ websearch_to_tsquery(ic.fts_config::regconfig, :query) "
            "ORDER BY raw_score DESC, ic.id "
            "LIMIT :limit"
        )
        return self._run(command, sql, {"query": command.query})

    def _vector(
        self, command: RetrievalCommand, query_embedding_text: str
    ) -> tuple[RetrievedRow, ...]:
        sql = (
            f"SELECT {_COLUMN_LIST}, "
            "(1.0 - (ic.embedding <=> CAST(:query_embedding AS vector))) AS raw_score "
            + _BASE_SQL
            + "  AND ic.embedding IS NOT NULL "
            "ORDER BY ic.embedding <=> CAST(:query_embedding AS vector) ASC, ic.id "
            "LIMIT :limit"
        )
        return self._run(command, sql, {"query_embedding": query_embedding_text})

    def _run(
        self, command: RetrievalCommand, sql: str, params: dict[str, object]
    ) -> tuple[RetrievedRow, ...]:
        params = {
            **params,
            "notebook_id": command.notebook_id,
            "actor_user_id": command.actor_user_id,
            "allow_pinned_versions": command.source_version_ids is not None,
        }
        if command.source_ids is not None:
            sql = sql.replace("WHERE", "  AND s.id = ANY(:source_ids)\nWHERE", 1)
            params["source_ids"] = list(command.source_ids)
        if command.source_version_ids is not None:
            sql = sql.replace(
                "WHERE", "  AND ic.source_version_id = ANY(:source_version_ids)\nWHERE", 1
            )
            params["source_version_ids"] = list(command.source_version_ids)
        limits = self._overfetch_limits(command.top_k)
        for index, limit in enumerate(limits):
            params["limit"] = limit
            try:
                rows = self._fetch(sql, params)
            except sa.exc.ProgrammingError:
                logger.warning(
                    "retrieval query rejected (bad query syntax); returning empty: notebook=%s",
                    command.notebook_id,
                )
                return ()
            survivors = self._policy_recheck(command, rows)
            if len(survivors) >= command.top_k or limit == limits[-1]:
                return tuple(survivors[: command.top_k])
            logger.info(
                "retrieval under-return: %d/%d after policy re-check; increasing limit to %d",
                len(survivors),
                command.top_k,
                limits[index + 1],
            )
        raise AssertionError("unreachable: over-fetch loop must return")

    def _fetch(self, sql: str, params: dict[str, object]) -> list[sa.engine.RowMapping]:
        with self._engine.begin() as connection:
            result = connection.execute(sa.text(sql), params)
            return list(result.mappings())

    def _policy_recheck(
        self, command: RetrievalCommand, rows: Sequence[sa.engine.RowMapping]
    ) -> list[RetrievedRow]:
        """Drop access-denied rows (all-users or per-user) and log each deny."""
        if not rows:
            return []
        version_ids = sorted({row["source_version_id"] for row in rows})
        with self._engine.begin() as connection:
            denied = {
                row[0]
                for row in connection.execute(
                    sa.text(
                        """
                        SELECT source_version_id FROM source_restrictions
                        WHERE restriction_type = 'access_denied'
                          AND source_version_id = ANY(:version_ids)
                          AND (user_id IS NULL OR user_id = :actor_user_id)
                        """
                    ),
                    {"version_ids": version_ids, "actor_user_id": command.actor_user_id},
                )
            }
        survivors: list[RetrievedRow] = []
        for position, row in enumerate(rows, start=1):
            if row["source_version_id"] in denied:
                logger.warning(
                    "post-hydration policy deny: chunk=%s source_version=%s actor=%s",
                    row["id"],
                    row["source_version_id"],
                    command.actor_user_id,
                )
                continue
            survivors.append(
                RetrievedRow(
                    chunk_id=row["id"],
                    notebook_id=row["notebook_id"],
                    source_id=row["source_id"],
                    source_version_id=row["source_version_id"],
                    source_title=row["display_title"],
                    canonical_node_id=row["canonical_node_id"],
                    char_start=row["char_start"],
                    char_end=row["char_end"],
                    text=row["text"],
                    token_count=row["token_count"],
                    language=row["language"],
                    section_ancestry=self._parse_ancestry(row["section_ancestry"]),
                    node_spans=self._parse_spans(row["node_spans"]),
                    raw_score=float(row["raw_score"]),
                    retriever_rank=position,
                )
            )
        return survivors

    @staticmethod
    def _parse_ancestry(raw: str | list[str]) -> tuple[uuid.UUID, ...]:
        values = raw if isinstance(raw, list) else json.loads(raw)
        return tuple(uuid.UUID(value) for value in values)

    @staticmethod
    def _parse_spans(raw: str | list[dict[str, object]]) -> tuple[NodeSpan, ...]:
        values = raw if isinstance(raw, list) else json.loads(raw)
        return tuple(
            NodeSpan(
                node_id=uuid.UUID(str(item["node_id"])),
                char_start=int(str(item["char_start"])),
                char_end=int(str(item["char_end"])),
            )
            for item in values
        )
