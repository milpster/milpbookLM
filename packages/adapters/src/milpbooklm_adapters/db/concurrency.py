"""
Serializable/advisory-lock sections for cross-row invariants (FND-03 micro-index 3.4).

ch05: "Service logic plus serializable/advisory-lock sections protect cross-row rules such as
final-owner removal, active-version swap and idempotency-key creation. Deadlock/serialization
failures use bounded whole-transaction retries."

Each section takes an open psycopg connection, is the FIRST statement batch in a fresh
transaction (SET TRANSACTION ... then pg_advisory_xact_lock), and commits at the end.
BoundedRetry re-runs the whole transaction on 40001/40P01 with exponential backoff.
"""

from __future__ import annotations

import dataclasses
import time
import uuid
from collections.abc import Callable

import psycopg

# 63-bit advisory-lock namespace for per-entity locks: high bits = entity kind.
_LOCK_KIND_FINAL_OWNER = 0x01
_LOCK_KIND_ACTIVE_SWAP = 0x02

_SERIALIZABLE_TRANSACTION = "SET TRANSACTION ISOLATION LEVEL SERIALIZABLE, READ WRITE"

_RETRYABLE_SQLSTATE = frozenset({"40001", "40P01"})  # serialization_failure, deadlock_detected


class ConcurrencyError(RuntimeError):
    """Base class for cross-row invariant violations raised inside a section."""


class FinalOwnerRemovalBlockedError(ConcurrencyError):
    """Removing the last owner membership without locked administrative custody."""


class ActiveSwapConflictError(ConcurrencyError):
    """The atomic active-version swap lost to a concurrent swap."""


@dataclasses.dataclass(frozen=True, slots=True)
class BoundedRetry:
    """Whole-transaction retry with exponential backoff for serialization/deadlock failures."""

    max_attempts: int = 3
    base_delay_ms: int = 25

    def call(self, operation: Callable[[], object]) -> object:
        """Run operation; retry the whole transaction on 40001/40P01, bounded."""
        delay_ms = self.base_delay_ms
        for attempt in range(1, self.max_attempts + 1):
            try:
                return operation()
            except psycopg.OperationalError as exc:
                sqlstate = getattr(exc, "pgcode", None)
                if sqlstate not in _RETRYABLE_SQLSTATE or attempt == self.max_attempts:
                    raise
                time.sleep(delay_ms / 1000.0)
                delay_ms *= 2
        raise AssertionError("unreachable: bounded retry exhausted")


def _stable_lock_key(kind: int, entity_id: uuid.UUID) -> int:
    """Map (kind, entity uuid) into a 63-bit signed advisory-lock key."""
    entity_bits = int.from_bytes(entity_id.bytes, "big") & ((1 << 62) - 1)
    return ((kind & 0xFF) << 62) | entity_bits


def remove_final_owner(
    conn: psycopg.Connection, *, notebook_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    """
    Remove an owner membership iff the notebook keeps an owner or enters custody.

    Serialized per notebook (advisory xact lock) so two concurrent removals cannot
    both read "one owner left" and both proceed; the serializable level makes any
    interleaved ownership change surface as 40001 and retry.
    """
    conn.execute(_SERIALIZABLE_TRANSACTION)
    conn.execute(
        "SELECT pg_advisory_xact_lock(%s)",
        (_stable_lock_key(_LOCK_KIND_FINAL_OWNER, notebook_id),),
    )
    owners_row = conn.execute(
        "SELECT COUNT(*) FROM notebook_memberships WHERE notebook_id = %s AND role = 'owner'",
        (notebook_id,),
    ).fetchone()
    owners = int(owners_row[0]) if owners_row is not None else 0
    is_owner_row = conn.execute(
        "SELECT EXISTS (SELECT 1 FROM notebook_memberships WHERE notebook_id = %s "
        "AND user_id = %s AND role = 'owner')",
        (notebook_id, user_id),
    ).fetchone()
    is_owner = bool(is_owner_row[0]) if is_owner_row is not None else False
    if not is_owner:
        raise ConcurrencyError(f"user {user_id} is not an owner of notebook {notebook_id}")
    if owners == 1:
        custody_row = conn.execute(
            "SELECT custody_state FROM notebooks WHERE id = %s", (notebook_id,)
        ).fetchone()
        custody = custody_row[0] if custody_row is not None else None
        if custody != "locked_admin_custody":
            raise FinalOwnerRemovalBlockedError(
                f"notebook {notebook_id} has a single owner and no locked administrative custody"
            )
        conn.execute(
            "UPDATE notebooks SET custody_state = 'none', updated_at = now() WHERE id = %s",
            (notebook_id,),
        )
    conn.execute(
        "DELETE FROM notebook_memberships WHERE notebook_id = %s AND user_id = %s "
        "AND role = 'owner'",
        (notebook_id, user_id),
    )
    conn.commit()


def swap_active_source_version(
    conn: psycopg.Connection, *, source_id: uuid.UUID, new_version_id: uuid.UUID
) -> None:
    """
    Atomically activate new_version_id and deactivate the current active version.

    One transaction + per-source advisory lock: the partial unique index guarantees
    at most one active version, so the swap is all-or-nothing even under races.
    """
    conn.execute(_SERIALIZABLE_TRANSACTION)
    conn.execute(
        "SELECT pg_advisory_xact_lock(%s)",
        (_stable_lock_key(_LOCK_KIND_ACTIVE_SWAP, source_id),),
    )
    current = conn.execute(
        "SELECT id FROM source_versions WHERE source_id = %s AND status = 'active'", (source_id,)
    ).fetchone()
    if current is not None and current[0] != new_version_id:
        conn.execute(
            "UPDATE source_versions SET status = 'inactive' WHERE id = %s", (current[0],)
        )
    updated = conn.execute(
        "UPDATE source_versions SET status = 'active', "
        "activated_at = COALESCE(activated_at, now()) WHERE id = %s AND source_id = %s",
        (new_version_id, source_id),
    ).rowcount
    if updated != 1:
        conn.rollback()
        raise ActiveSwapConflictError(
            f"version {new_version_id} is not a version of source {source_id}"
        )
    conn.execute(
        "UPDATE sources SET current_version_id = %s, updated_at = now() WHERE id = %s",
        (new_version_id, source_id),
    )
    conn.commit()


@dataclasses.dataclass(frozen=True, slots=True)
class IdempotencyResult:
    """Outcome of an idempotency-key claim: created means this caller owns the key."""

    created: bool
    key_id: uuid.UUID
    status: str


def claim_idempotency_key(
    conn: psycopg.Connection,
    *,
    scope: str,
    key: str,
    request_hash: str,
    ttl_seconds: int = 86400,
) -> IdempotencyResult:
    """
    Claim (scope, key); concurrent duplicates lose at the unique constraint and read the winner.

    The unique (scope, key) index is the concurrency protection: exactly one inserter
    succeeds, every loser re-reads the existing row in the same transaction.
    """
    inserted = conn.execute(
        "INSERT INTO idempotency_keys (scope, key, request_hash, status, expires_at) "
        "VALUES (%s, %s, %s, 'in_flight', now() + (%s || ' seconds')::interval) "
        "ON CONFLICT (scope, key) DO NOTHING RETURNING id, status",
        (scope, key, request_hash, str(ttl_seconds)),
    ).fetchone()
    if inserted is not None:
        conn.commit()
        return IdempotencyResult(created=True, key_id=inserted[0], status=inserted[1])
    existing = conn.execute(
        "SELECT id, status FROM idempotency_keys WHERE scope = %s AND key = %s", (scope, key)
    ).fetchone()
    conn.commit()
    if existing is None:  # winner expired/deleted between statements: try once more
        return claim_idempotency_key(
            conn, scope=scope, key=key, request_hash=request_hash, ttl_seconds=ttl_seconds
        )
    return IdempotencyResult(created=False, key_id=existing[0], status=existing[1])
