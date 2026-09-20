"""
PostgreSQL identity adapters: the users table + the append-only audit trail.

Prototype note (noted in task-4 evidence risks): the ch05 ``users`` table has no
installation-administrator column, so the flag is derived from the append-only
audit grant row written atomically with the account (action
``installation_admin.granted``). A ``users.is_installation_admin`` column is a
wave-2 migration (FND-02 territory), not a prototype gap.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from milpbooklm_application.ports import AuditRetentionReport, UserRecord
from milpbooklm_domain.identity import User, UserStatus

from milpbooklm_adapters.db.tables.blobs import audit_events
from milpbooklm_adapters.db.tables.identity import users

# The audit action whose presence (for a live user) marks the installation admin.
ADMIN_GRANT_ACTION = "installation_admin.granted"

_ADMIN_GRANT = sa.select(sa.func.count()).select_from(audit_events).where(
    audit_events.c.action == ADMIN_GRANT_ACTION,
    audit_events.c.subject_kind == "user",
    audit_events.c.subject_id == sa.bindparam("user_id"),
)


class PgUserRepository:
    """The users table adapter implementing the application UserRepository port."""

    def __init__(self, engine: sa.engine.Engine) -> None:
        """Wire the engine."""
        self._engine = engine

    def _user_from_row(self, row: sa.engine.Row[Any], *, admin: bool) -> User:
        """Build the domain User from a table row plus the resolved admin flag."""
        return User(
            id=row.id,
            email=row.email,
            display_name=row.display_name,
            status=UserStatus(row.status),
            installation_admin=admin,
            created_at=row.created_at,
        )

    def _is_admin(self, conn: sa.engine.Connection, user_id: uuid.UUID) -> bool:
        """Resolve the admin flag from the append-only audit grant row."""
        count = conn.execute(_ADMIN_GRANT, {"user_id": user_id}).scalar_one()
        return count > 0

    def create(
        self,
        *,
        email: str,
        display_name: str,
        password_hash: str,
        installation_admin: bool = False,
    ) -> User:
        """Create an account (atomically with its admin grant row); ValueError on duplicate."""
        with self._engine.begin() as conn:
            try:
                row = conn.execute(
                    sa.insert(users)
                    .values(email=email, display_name=display_name, password_hash=password_hash)
                    .returning(users.c.id, users.c.created_at)
                ).one()
            except sa.exc.IntegrityError:
                raise ValueError(f"email {email!r} is already registered") from None
            if installation_admin:
                conn.execute(
                    sa.insert(audit_events).values(
                        actor_user_id=row.id,
                        action=ADMIN_GRANT_ACTION,
                        subject_kind="user",
                        subject_id=row.id,
                        details={"via": "bootstrap"},
                    )
                )
        return User(
            id=row.id,
            email=email,
            display_name=display_name,
            status=UserStatus.ACTIVE,
            installation_admin=installation_admin,
            created_at=row.created_at,
        )

    def get(self, user_id: uuid.UUID) -> User | None:
        """Return the account, or None."""
        with self._engine.begin() as conn:
            row = conn.execute(
                sa.select(users.c.id, users.c.email, users.c.display_name, users.c.status,
                          users.c.created_at).where(users.c.id == user_id)
            ).first()
            if row is None:
                return None
            return self._user_from_row(row, admin=self._is_admin(conn, user_id))

    def get_by_email(self, email: str) -> User | None:
        """Return the account for the exact email, or None."""
        with self._engine.begin() as conn:
            row = conn.execute(
                sa.select(users.c.id, users.c.email, users.c.display_name, users.c.status,
                          users.c.created_at).where(users.c.email == email)
            ).first()
            if row is None:
                return None
            return self._user_from_row(row, admin=self._is_admin(conn, row.id))

    def get_record(self, email: str) -> UserRecord | None:
        """Return the account with its stored hash (login path only), or None."""
        with self._engine.begin() as conn:
            row = conn.execute(
                sa.select(
                    users.c.id, users.c.email, users.c.display_name, users.c.status,
                    users.c.password_hash, users.c.created_at,
                ).where(users.c.email == email)
            ).first()
            if row is None:
                return None
            user = self._user_from_row(row, admin=self._is_admin(conn, row.id))
            return UserRecord(user=user, password_hash=row.password_hash)

    def set_status(self, user_id: uuid.UUID, status: UserStatus) -> User:
        """Move the account to a new lifecycle status; return the updated account."""
        with self._engine.begin() as conn:
            result = conn.execute(
                sa.update(users)
                .where(users.c.id == user_id)
                .values(status=status.value, revision=users.c.revision + 1)
            )
            if result.rowcount == 0:
                raise ValueError(f"unknown user {user_id}")
        updated = self.get(user_id)
        if updated is None:
            msg = f"user {user_id} disappeared after status update"
            raise ValueError(msg)
        return updated

    def count(self) -> int:
        """Count accounts (bootstrap one-time guard)."""
        with self._engine.begin() as conn:
            return conn.execute(sa.select(sa.func.count()).select_from(users)).scalar_one()

    def any_installation_admin(self) -> bool:
        """Whether a live installation administrator exists (bootstrap one-time guard)."""
        with self._engine.begin() as conn:
            count = conn.execute(
                sa.select(sa.func.count())
                .select_from(audit_events)
                .join(users, users.c.id == audit_events.c.subject_id)
                .where(
                    audit_events.c.action == ADMIN_GRANT_ACTION,
                    audit_events.c.subject_kind == "user",
                    users.c.status == UserStatus.ACTIVE.value,
                )
            ).scalar_one()
        return count > 0


class PgAuditLog:
    """The audit_events table adapter implementing the application AuditLog port."""

    def __init__(self, engine: sa.engine.Engine) -> None:
        """Wire the engine."""
        self._engine = engine

    def record(
        self,
        *,
        actor_id: uuid.UUID | None,
        action: str,
        subject_kind: str | None = None,
        subject_id: uuid.UUID | None = None,
        details: dict[str, str] | None = None,
        request_id: str | None = None,
    ) -> None:
        """Append one audited event (metadata only; content never enters audit rows)."""
        with self._engine.begin() as conn:
            conn.execute(
                sa.insert(audit_events).values(
                    actor_user_id=actor_id,
                    action=action,
                    subject_kind=subject_kind,
                    subject_id=subject_id,
                    details=details,
                    request_id=request_id,
                )
            )

    def retention_report(self, *, cutoff: datetime) -> AuditRetentionReport:
        """
        Report the append-only events eligible for out-of-band purging.

        Conservative by design: the app role cannot UPDATE/DELETE audit rows (the
        immutability trigger is authoritative), so this only SELECTs the events
        created before ``cutoff`` and reports their range - it never mutates
        retained events. Physical purging is a privileged operation.
        """
        with self._engine.begin() as conn:
            row = conn.execute(
                sa.select(
                    sa.func.count().label("eligible"),
                    sa.func.min(audit_events.c.created_at).label("oldest"),
                    sa.func.max(audit_events.c.created_at).label("newest"),
                ).where(audit_events.c.created_at < cutoff)
            ).one()
        return AuditRetentionReport(
            eligible_count=int(row.eligible),
            cutoff=cutoff,
            oldest_created=row.oldest,
            newest_created=row.newest,
        )
