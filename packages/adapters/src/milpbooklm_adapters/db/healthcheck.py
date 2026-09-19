"""
Readiness and extension checks (FND-03 micro-index 3.1.2, ch04 "Health").

The API readiness stays false during incompatible schema states: this check verifies the
PostgreSQL 18 major, the pgvector extension, the uuidv7() database id function (TAD-011)
and the alembic version, all under the app role (DML/SELECT only).
"""

from __future__ import annotations

import dataclasses
import re

import psycopg

REQUIRED_MAJOR = 18
REQUIRED_EXTENSIONS = ("vector",)


@dataclasses.dataclass(frozen=True, slots=True)
class ReadinessReport:
    """Outcome of a readiness probe: server version, extensions, id function, alembic version."""

    server_version: str
    server_major: int
    extensions: tuple[str, ...]
    uuidv7_available: bool
    alembic_version: str | None

    @property
    def ready(self) -> bool:
        """True when the PG18 major, pgvector and uuidv7() checks all hold."""
        return self.server_major == REQUIRED_MAJOR and all(
            ext in self.extensions for ext in REQUIRED_EXTENSIONS
        ) and self.uuidv7_available


class ReadinessError(RuntimeError):
    """Raised when the deployment is not ready to serve traffic."""


def check_readiness(dsn: str) -> ReadinessReport:
    """Probe the app DSN: PG18 major, pgvector, uuidv7(), current alembic version."""
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        version_row = conn.execute("SELECT current_setting('server_version')").fetchone()
        version_raw: str = version_row[0] if version_row is not None else ""
        match = re.match(r"(\d+)", version_raw)
        if match is None:
            raise ReadinessError(f"unparseable server version: {version_raw!r}")
        major = int(match.group(1))
        extensions = tuple(
            row[0]
            for row in conn.execute("SELECT extname FROM pg_extension ORDER BY extname")
        )
        uuid_row = conn.execute(
            "SELECT (uuidv7()::text) ~* '^[0-9a-f]{8}-[0-9a-f]{4}-7'"
        ).fetchone()
        uuidv7_available = bool(uuid_row[0]) if uuid_row is not None else False
        version_row = conn.execute(
            "SELECT version_num FROM alembic_version LIMIT 1"
        ).fetchone()
    report = ReadinessReport(
        server_version=version_raw,
        server_major=major,
        extensions=extensions,
        uuidv7_available=uuidv7_available,
        alembic_version=version_row[0] if version_row else None,
    )
    if not report.ready:
        raise ReadinessError(f"database not ready: {report}")
    return report
