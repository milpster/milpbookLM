from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from milpbooklm_adapters.blobs import FilesystemBlobStore, PgBlobRepository
from milpbooklm_adapters.db.connections import make_engine
from milpbooklm_adapters.grounding import PgGroundingStore
from milpbooklm_adapters.security.clock import SystemClock
from milpbooklm_adapters.sources import PgSourcePurge
from milpbooklm_application.source_lifecycle import NoOpBackupExpiryScheduler

from tests.domain.invariants._factories import Db


def test_purge_erases_identity_closure_and_blocks_citation_immediately(
    tmp_path: Path,
) -> None:
    socket_dir = Path("scratch/t13-smoke")
    if not (socket_dir / ".s.PGSQL.29521").exists():
        pytest.skip("live PostgreSQL acceptance stack is not running")
    app_dsn = (
        "postgresql://milpbooklm_app:milpbooklm_app@/milpbooklm_t13"
        f"?host={socket_dir.resolve()}&port=29521"
    )
    db = Db(app_dsn)
    actor_id = db.user()
    notebook_id = db.notebook(actor_id)
    source_id = db.source(notebook_id, actor_id)
    source_version_id = db.source_version(source_id, actor_id, status="activating")
    engine = make_engine(app_dsn.replace("postgresql://", "postgresql+psycopg://"))
    blobs = FilesystemBlobStore(tmp_path, PgBlobRepository(engine), SystemClock())
    blob = blobs.put(
        f"privacy purge content {source_id}".encode(),
        content_type="text/plain",
        referrer_kind="source_version",
        referrer_id=source_version_id,
    )
    document_id = uuid.uuid4()
    node_id = uuid.uuid4()
    locator_id = uuid.uuid4()
    manifest_id = db.manifest(notebook_id=notebook_id, created_by=actor_id)
    conversation_id = db.conversation(actor_id, notebook_id=notebook_id)
    message_id = uuid.uuid4()
    artifact_id = db.artifact(notebook_id, actor_id)
    artifact_version_id = db.artifact_version(artifact_id, manifest_id, actor_id)
    generation_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE source_versions SET original_blob_id=:blob, status='active', "
                "activated_at=now() WHERE id=:version"
            ),
            {"blob": blob.id, "version": source_version_id},
        )
        connection.execute(
            sa.text("UPDATE sources SET current_version_id=:version WHERE id=:source"),
            {"version": source_version_id, "source": source_id},
        )
        connection.execute(
            sa.text(
                "INSERT INTO canonical_documents "
                "(id, source_version_id, canonical_schema_version, parser_identity, "
                "parser_version, parser_profile, tool_versions, contract_json, active) "
                "VALUES (:id,:version,'1','test','1','test','{}','{}',true)"
            ),
            {"id": document_id, "version": source_version_id},
        )
        connection.execute(
            sa.text(
                "INSERT INTO canonical_nodes "
                "(id, canonical_document_id, node_type, seq, text_content, "
                "structural_identity, authority_class) "
                "VALUES (:id,:document,'paragraph',1,'privacy purge content','p:1','direct')"
            ),
            {"id": node_id, "document": document_id},
        )
        connection.execute(
            sa.text(
                "INSERT INTO canonical_locators "
                "(id, canonical_node_id, locator_kind, char_start, char_end, structural_path) "
                "VALUES (:id,:node,'char_range',0,21,'[]')"
            ),
            {"id": locator_id, "node": node_id},
        )
        connection.execute(
            sa.text(
                "INSERT INTO generation_manifest_items "
                "(id, manifest_id, item_kind, item_id) "
                "VALUES (:id,:manifest,'source_version',:version)"
            ),
            {
                "id": uuid.uuid4(),
                "manifest": manifest_id,
                "version": source_version_id,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO messages "
                "(id, conversation_id, role, content, manifest_id, citations) "
                "VALUES (:id,:conversation,'assistant','derived body',:manifest,'[]')"
            ),
            {
                "id": message_id,
                "conversation": conversation_id,
                "manifest": manifest_id,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO index_generations "
                "(id, notebook_id, source_id, source_version_id, chunker_profile, "
                "chunker_revision, embedding_model, embedding_dimension, "
                "embedding_normalization, fusion_config_version, status, manifest) "
                "VALUES (:id,:notebook,:source,:version,'structural','1','test',1024,"
                "'l2','1','ready','{}')"
            ),
            {
                "id": generation_id,
                "notebook": notebook_id,
                "source": source_id,
                "version": source_version_id,
            },
        )

    purge = PgSourcePurge(engine, NoOpBackupExpiryScheduler(), blobs)
    mark = purge.mark(source_id, actor_id)
    assert mark is not None
    assert PgGroundingStore(engine).jump(
        actor_user_id=actor_id,
        source_version_id=source_version_id,
        canonical_node_id=node_id,
    ) == {"state": "unavailable (purged)"}

    report = purge.erase(mark.task_id)

    assert report.task_id == mark.task_id
    with engine.begin() as connection:
        for table, column, identity in (
            ("canonical_documents", "id", document_id),
            ("index_generations", "id", generation_id),
            ("messages", "id", message_id),
            ("artifact_versions", "id", artifact_version_id),
            ("blob_objects", "id", blob.id),
        ):
            count = connection.scalar(
                sa.text(f"SELECT count(*) FROM {table} WHERE {column}=:identity"),
                {"identity": identity},
            )
            assert count == 0, table
    assert not (tmp_path / blob.storage_path).exists()
    db.conn.close()
