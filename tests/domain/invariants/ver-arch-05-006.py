"""ARCH-05-006: a committed message is immutable except for the explicit privacy
deletion (tombstone), which may be set once and never unset."""

from __future__ import annotations

import dataclasses
import uuid

import psycopg
import pytest
from milpbooklm_domain.conversations import Message

from tests.domain.invariants._factories import Db
from tests.domain.invariants._ver import write_ver


def test_arch_05_006_message_immutable_except_tombstone(pg_env: dict[str, str]) -> None:
    # Domain: the message value object is frozen.
    message = Message(id=uuid.uuid4(), role="user", content="hi", manifest_id=uuid.uuid4())
    with pytest.raises(dataclasses.FrozenInstanceError):
        message.content = "mutated"  # type: ignore[misc]
    assert dataclasses.replace(message, tombstoned=True).tombstoned is True

    # DB: the tombstone guard trigger allows only the tombstone pair, set once.
    db = Db(pg_env["app"])
    try:
        user = db.user()
        conversation = db.conversation(user)
        manifest = db.manifest(notebook_id=None, created_by=user)
        message_id = db.message(conversation, manifest, sender=user, content="secret answer")

        for column, value in (
            ("content", "mutated"),
            ("role", "assistant"),
            ("manifest_id", db.manifest(created_by=user)),
        ):
            with pytest.raises(psycopg.Error):
                db.conn.execute(f"UPDATE messages SET {column} = %s WHERE id ="
                    " %s", (value, message_id))

        # Tombstone set once: the paired reason is required, the set is allowed...
        with pytest.raises(psycopg.IntegrityError):
            db.conn.execute("UPDATE messages SET tombstone_at = now() WHERE id = %s", (message_id,))
        db.conn.execute(
            "UPDATE messages SET tombstone_at = now(), tombstone_reason = 'user privacy deletion'"
                " WHERE id = %s",
            (message_id,),
        )
        # ...and may never be unset; content still immutable afterwards.
        with pytest.raises(psycopg.Error):
            db.conn.execute("UPDATE messages SET tombstone_at = NULL, tombstone_reason = NULL"
                " WHERE id = %s", (message_id,))
        with pytest.raises(psycopg.Error):
            db.conn.execute("UPDATE messages SET content = 'x' WHERE id = %s", (message_id,))
    finally:
        db.close()
    write_ver(
        verification_id="VER-ARCH-05-006",
        requirement_id="ARCH-05-006",
        test_path="tests/domain/invariants/ver-arch-05-006.py",
        checks={
            "domain_frozen": "Message is a frozen dataclass; replace() is the only copy path",
            "db_content_immutable": "UPDATE content/role/manifest_id all rejected by"
                " trg_messages_tombstone_guard",
            "tombstone_set_once": "tombstone_at requires the paired reason, is settable once,"
                " never unsettable",
        },
    )
