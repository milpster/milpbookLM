"""ARCH-05-016: a materialized generation manifest is immutable and its fingerprint is
stable; agent runs create NEW child manifests instead of mutating the parent."""

from __future__ import annotations

import uuid

import psycopg
import pytest
from milpbooklm_domain.manifests import (
    GenerationInputManifest,
    ManifestItem,
    OperationKind,
    manifest_fingerprint,
)
from milpbooklm_domain.notes import ContentKind

from tests.domain.invariants._factories import Db
from tests.domain.invariants._ver import write_ver


def _manifest(op: OperationKind = OperationKind.AGENTIC_CHAT) -> GenerationInputManifest:
    return GenerationInputManifest(
        id=uuid.uuid4(),
        op_kind=op,
        config_snapshot={"instructions": "be precise", "mode": "agentic"},
        items=(
            ManifestItem(
                kind=ContentKind.EVIDENCE_SNAPSHOT, item_id=uuid.uuid4(), item_sha256="f" * 64
            ),
        ),
    )


def test_arch_05_016_manifest_immutable_fingerprint_stable(pg_env: dict[str, str]) -> None:
    # Domain: the fingerprint is stable for an unchanged manifest and flips on any change.
    manifest = _manifest()
    first = manifest_fingerprint(manifest)
    assert first == manifest_fingerprint(manifest)  # stable across calls
    changed_item = ManifestItem(
        kind=ContentKind.EVIDENCE_SNAPSHOT, item_id=uuid.uuid4(), item_sha256="0" * 64
    )
    changed = GenerationInputManifest(
        id=manifest.id,
        op_kind=manifest.op_kind,
        config_snapshot=manifest.config_snapshot,
        items=(changed_item,),
    )
    assert manifest_fingerprint(changed) != first  # silent change flips the fingerprint

    # DB: the manifest rows are immutable (update and delete rejected by the trigger).
    db = Db(pg_env["app"])
    try:
        user = db.user()
        notebook = db.notebook(user)
        manifest_id = db.manifest(op_kind="agentic_chat", notebook_id=notebook, created_by=user)
        with pytest.raises(psycopg.Error):
            db.conn.execute(
                "UPDATE generation_input_manifests SET config_snapshot = %s WHERE id = %s",
                ('{"mode": "ordinary"}', manifest_id),
            )
        with pytest.raises(psycopg.Error):
            db.conn.execute("DELETE FROM generation_input_manifests WHERE id = %s", (manifest_id,))
        # A child manifest is the sanctioned way to evolve: a NEW immutable row, born with
        # its parent link (parent_manifest_id is immutable like the rest of the row).
        child_id = db.manifest(
            op_kind="agentic_chat",
            notebook_id=notebook,
            created_by=user,
            parent_manifest_id=manifest_id,
        )
        link = db.conn.execute(
            "SELECT parent_manifest_id FROM generation_input_manifests WHERE id = %s", (child_id,)
        ).fetchone()[0]
        assert link == manifest_id  # child references the parent, parent unchanged
    finally:
        db.close()
    write_ver(
        verification_id="VER-ARCH-05-016",
        requirement_id="ARCH-05-016",
        test_path="tests/domain/invariants/ver-arch-05-016.py",
        checks={
            "fingerprint_stable": "manifest_fingerprint is stable for an unchanged manifest",
            "fingerprint_sensitive": "a silent content change flips the fingerprint",
            "db_immutable": "manifest UPDATE/DELETE rejected by"
                " trg_generation_input_manifests_immutable",
            "child_manifest": "an agent run evolves via a NEW child manifest (parent_manifest_id),"
                " not a mutation",
        },
    )
