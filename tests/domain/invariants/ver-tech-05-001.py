"""TECH-05-001: uuid PKs, database-side uuidv7() defaults, timestamptz, revision/etag,
outbox events commit in the same transaction as their aggregate."""

from __future__ import annotations

import re
import uuid

import psycopg
from milpbooklm_adapters.db.schema import METADATA

from tests.domain.invariants._factories import Db
from tests.domain.invariants._ver import write_ver

UUIDV7_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-7")

# Mutable roots carrying the optimistic-concurrency pair (TECH-05-001).
MUTABLE_ROOTS = ("users", "notebooks", "sources", "notes", "conversations", "artifacts")
# Primary keys that are deliberately not uuid (catalog/text keys, alembic bookkeeping).
NON_UUID_PKS = {"migration_metadata", "alembic_version"}


def test_tech_05_001_id_timestamps_and_outbox_transaction(pg_env: dict[str, str]) -> None:
    db = Db(pg_env["app"])
    try:
        # 1. Every schema table has a uuid primary key, except the text/varchar catalog keys.
        rows = db.conn.execute(
            "SELECT c.relname, t.typname FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "JOIN pg_constraint con ON con.conrelid = c.oid AND con.contype = 'p' "
            "JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = ANY (con.conkey) "
            "JOIN pg_type t ON t.oid = a.atttypid "
            "WHERE n.nspname = 'public'"
        ).fetchall()
        pk_types = dict(rows)
        uuid_pk_tables = {name for name, typ in pk_types.items() if typ == "uuid"}
        assert uuid_pk_tables == set(METADATA.tables) - NON_UUID_PKS

        # 2. The uuid primary keys default to the database-side uuidv7() (TAD-011).
        default = db.conn.execute(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_name = 'users' AND column_name = 'id'"
        ).fetchone()[0]
        assert default == "uuidv7()"
        fresh = db.conn.execute(
            "INSERT INTO users (email, display_name, password_hash) "
            "VALUES (%s, %s, %s) RETURNING id",
            (f"fresh-{uuid.uuid4().hex[:16]}@example.invalid", "Fresh", "hash"),
        ).fetchone()[0]
        assert UUIDV7_RE.match(str(fresh)) is not None
        db.conn.execute("DELETE FROM users WHERE id = %s", (fresh,))

        # 3. UTC timestamptz columns, database-defaulted.
        types = dict(db.conn.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = 'users' AND column_name IN ('created_at', 'updated_at')"
            ).fetchall())
        assert types == {"created_at": "timestamp with time"
            " zone", "updated_at": "timestamp with time zone"}

        # 4. Mutable roots carry the integer revision + etag compare-and-swap pair.
        for table in MUTABLE_ROOTS:
            pair = dict(
                db.conn.execute(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_name = %s AND column_name IN ('revision', 'etag')",
                    (table,),
                ).fetchall()
            )
            assert pair == {"revision": "integer", "etag": "text"}, table

        # 5. Outbox event commits in the same transaction as its aggregate: a rollback
        # removes BOTH (no cross-transaction coupling).
        with psycopg.connect(pg_env["app"]) as conn:  # autocommit=False
            user = conn.execute(
                "INSERT INTO users (id, email, display_name, password_hash) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (uuid.uuid4(), f"outbox-{uuid.uuid4().hex[:16]}@example.invalid", "Outbox", "hash"),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO outbox_events (aggregate_kind, aggregate_id, event_type, payload) "
                "VALUES ('notebook', %s, 'notebook.created', %s)",
                (user, '{"notebook_id": null}'),
            )
            conn.rollback()
        assert db.conn.execute("SELECT 1 FROM users WHERE id = %s", (user,)).fetchone() is None
        pending = db.conn.execute("SELECT count(*) FROM outbox_events WHERE aggregate_id ="
            " %s", (user,)).fetchone()[0]
        assert pending == 0
    finally:
        db.close()
    write_ver(
        verification_id="VER-TECH-05-001",
        requirement_id="TECH-05-001",
        test_path="tests/domain/invariants/ver-tech-05-001.py",
        checks={
            "uuid_primary_keys": f"{len(uuid_pk_tables)} tables have uuid PKs (non-uuid"
                " exceptions: {sorted(NON_UUID_PKS)})",
            "uuidv7_default": "users.id column_default = uuidv7(); a fresh insert returns a"
                " version-7 uuid",
            "timestamptz": "users.created_at/updated_at are timestamp with time zone",
            "revision_etag": f"integer revision + text etag present on {list(MUTABLE_ROOTS)}",
            "outbox_same_transaction": "aggregate insert + outbox event rolled back together",
        },
    )
