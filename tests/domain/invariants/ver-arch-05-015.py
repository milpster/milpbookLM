"""ARCH-05-015: every committed model-generated output pins exactly one immutable
manifest - the manifest foreign key is NOT NULL and enforced on messages and
artifact versions."""

from __future__ import annotations

import uuid

import psycopg
import pytest
from milpbooklm_domain.manifests import GenerationInputManifest, ManifestItem, OperationKind
from milpbooklm_domain.notes import ContentKind

from tests.domain.invariants._factories import Db
from tests.domain.invariants._ver import write_ver


def test_arch_05_015_committed_output_pins_manifest(pg_env: dict[str, str]) -> None:
    # Domain: the manifest pins exact input items; op_kind must be a valid operation.
    manifest = GenerationInputManifest(
        id=uuid.uuid4(),
        op_kind=OperationKind.ORDINARY_CHAT,
        config_snapshot={"instructions": None, "mode": "ordinary"},
        items=(
            ManifestItem(
                kind=ContentKind.SOURCE_VERSION, item_id=uuid.uuid4(), item_sha256="e" * 64
            ),
        ),
    )
    assert manifest.op_kind is OperationKind.ORDINARY_CHAT
    assert manifest.items[0].kind is ContentKind.SOURCE_VERSION
    assert len(manifest.items) == 1

    # DB: the manifest pin is NOT NULL on both committed-output tables, and a real pin
    # must reference an existing manifest (FK enforced).
    db = Db(pg_env["app"])
    try:
        user = db.user()
        notebook = db.notebook(user)
        conversation = db.conversation(user, notebook_id=notebook)
        manifest_id = db.manifest(op_kind="ordinary_chat", notebook_id=notebook, created_by=user)
        artifact = db.artifact(notebook, user)

        # A committed message MUST pin a manifest (NOT NULL).
        with pytest.raises(psycopg.IntegrityError):
            db.conn.execute(
                "INSERT INTO messages (id, conversation_id, role, content, manifest_id) "
                "VALUES (%s, %s, 'assistant', 'answer', NULL)",
                (uuid.uuid4(), conversation),
            )
        # A committed message pinning a non-existent manifest is rejected (FK).
        with pytest.raises(psycopg.IntegrityError):
            db.conn.execute(
                "INSERT INTO messages (id, conversation_id, role, content, manifest_id) "
                "VALUES (%s, %s, 'assistant', 'answer', %s)",
                (uuid.uuid4(), conversation, uuid.uuid4()),
            )
        # A valid pin is accepted.
        message_id = db.message(conversation, manifest_id, role="assistant", content="answer")
        pinned = db.conn.execute("SELECT manifest_id FROM messages WHERE id ="
            " %s", (message_id,)).fetchone()[0]
        assert pinned == manifest_id

        # An artifact version MUST pin a manifest (NOT NULL) and the FK is enforced.
        with pytest.raises(psycopg.IntegrityError):
            db.conn.execute(
                "INSERT INTO artifact_versions (id, artifact_id, version_number, recipe_version,"
                    " manifest_id, "
                "created_by_user_id) VALUES (%s, %s, 1, '1', NULL, %s)",
                (uuid.uuid4(), artifact, user),
            )
        with pytest.raises(psycopg.IntegrityError):
            db.conn.execute(
                "INSERT INTO artifact_versions (id, artifact_id, version_number, recipe_version,"
                    " manifest_id, "
                "created_by_user_id) VALUES (%s, %s, 1, '1', %s, %s)",
                (uuid.uuid4(), artifact, uuid.uuid4(), user),
            )
    finally:
        db.close()
    write_ver(
        verification_id="VER-ARCH-05-015",
        requirement_id="ARCH-05-015",
        test_path="tests/domain/invariants/ver-arch-05-015.py",
        checks={
            "domain_manifest": "GenerationInputManifest pins exact input items with a valid"
                " op_kind",
            "message_pin_not_null": "messages.manifest_id NOT NULL; FK enforced; valid pin"
                " accepted",
            "artifact_pin_not_null": "artifact_versions.manifest_id NOT NULL; FK enforced",
        },
    )
