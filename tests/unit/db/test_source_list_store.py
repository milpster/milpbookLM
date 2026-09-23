from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from milpbooklm_adapters.db.connections import make_engine
from milpbooklm_adapters.sources.pg_sources import PgSourceCatalog

from tests.domain.invariants._factories import Db


def _scratch_dsn() -> str | None:
    socket_dir = Path("scratch/t13-smoke")
    if not (socket_dir / ".s.PGSQL.29521").exists():
        return None
    return (
        "postgresql://milpbooklm_app:milpbooklm_app@/milpbooklm_t13"
        f"?host={socket_dir.resolve()}&port=29521"
    )


@pytest.fixture(name="pg")
def _pg() -> Db:
    dsn = _scratch_dsn()
    if dsn is None:
        pytest.skip("live PostgreSQL acceptance stack is not running")
    return Db(dsn)


def test_list_sources_reads_latest_persisted_version_after_store_recreation(pg: Db) -> None:
    # Given
    actor = pg.user()
    notebook = pg.notebook(actor)
    source = pg.source(notebook, actor)
    _ = pg.source_version(source, actor, version_number=1, status="active")
    latest = pg.source_version(source, actor, version_number=2, status="parsed")
    dsn = _scratch_dsn()
    assert dsn is not None
    engine = make_engine(dsn.replace("postgresql://", "postgresql+psycopg://"))

    # When
    persisted = PgSourceCatalog(engine).list(notebook, actor)

    # Then
    assert len(persisted) == 1
    assert persisted[0].source_id == source
    assert persisted[0].source_version_id == latest
    assert PgSourceCatalog(engine).list(notebook, uuid.uuid4()) == []
