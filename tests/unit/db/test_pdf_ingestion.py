"""Real PDF acquisition, parsing, canonical persistence, and activation proof."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterable
from pathlib import Path

import anyio
import pytest
import sqlalchemy as sa
from milpbooklm_adapters.blobs import FilesystemBlobStore, PgBlobRepository
from milpbooklm_adapters.parsers.isolation import IsolatedParser, ParseFailure
from milpbooklm_adapters.parsers.pg_canonical import PgCanonicalRepository
from milpbooklm_adapters.security.clock import SystemClock
from milpbooklm_adapters.sources.filesystem_quarantine import FilesystemQuarantineStore
from milpbooklm_adapters.sources.pg_sources import PgSourceCatalog
from milpbooklm_application.source_acquisition import AcquireSource, AcquireSourceCommand
from milpbooklm_domain.jobs import JobRecord
from milpbooklm_workers.handlers import SourceParseHandler

from tests.domain.invariants._factories import Db

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "sources"
PDF_BYTES = (FIXTURES / "golden-pdf.pdf").read_bytes()
PDF_TEXT = "Quarterly revenue increased."


class _Audit:
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
        del actor_id, action, subject_kind, subject_id, details, request_id

    def retention_report(self, *, cutoff: object) -> object:
        del cutoff
        raise AssertionError("retention is not part of PDF acquisition")


class _Jobs:
    def __init__(self) -> None:
        self.job: JobRecord | None = None

    def enqueue(
        self, *, kind: str, payload: dict[str, object], **_: object
    ) -> tuple[JobRecord, bool]:
        self.job = JobRecord(
            id=uuid.uuid4(), kind=kind, queue="ingestion_indexing", payload=payload
        )
        return self.job, True


class _Context:
    def checkpoint(self, data: dict[str, object]) -> None:
        del data

    def progress(self, phase: str, fraction: float | None, status: str | None) -> None:
        del phase, fraction, status

    def should_stop(self) -> bool:
        return False


async def _one_chunk(data: bytes) -> AsyncIterable[bytes]:
    yield data


def test_invalid_pdf_bytes_are_rejected_even_when_declared_pdf() -> None:
    result = IsolatedParser().parse(uuid.uuid4(), "application/pdf", b"%PDF-1.7 invalid")

    assert isinstance(result, ParseFailure)
    assert result.state == "corrupt"


def _scratch_dsn() -> str | None:
    socket_dir = Path("scratch/t13-smoke")
    if not (socket_dir / ".s.PGSQL.29521").exists():
        return None
    return (
        "postgresql://milpbooklm_app:milpbooklm_app@/milpbooklm_t13"
        f"?host={socket_dir.resolve()}&port=29521"
    )


def test_real_pdf_upload_reaches_active_canonical_source(tmp_path: Path) -> None:
    # Given
    dsn = _scratch_dsn()
    if dsn is None:
        pytest.skip("live PostgreSQL acceptance stack is not running")
    db = Db(dsn)
    actor = db.user()
    notebook = db.notebook(actor)
    engine = sa.create_engine(dsn.replace("postgresql://", "postgresql+psycopg://"))
    blob_root = tmp_path / "blobs"
    blobs = FilesystemBlobStore(blob_root, PgBlobRepository(engine), SystemClock())
    acquire = AcquireSource(
        quarantine=FilesystemQuarantineStore(blob_root, max_bytes=1024 * 1024),
        blobs=blobs,
        catalog=PgSourceCatalog(engine),
        audit=_Audit(),
        jobs=_Jobs(),
    )

    # When: bytes are acquired, parsed by the real isolated child, then activated.
    view, created, _job_id = anyio.run(
        acquire,
        AcquireSourceCommand(
            notebook_id=notebook,
            actor_id=actor,
            display_title="Golden PDF",
            origin_kind="upload",
        ),
        _one_chunk(PDF_BYTES),
    )
    handler = SourceParseHandler(blobs, IsolatedParser(), PgCanonicalRepository(engine))
    parse_job = JobRecord(
        id=uuid.uuid4(),
        kind="ingestion.parse",
        queue="ingestion_indexing",
        payload={
            "source_id": str(view.source_id),
            "source_version_id": str(view.source_version_id),
            "blob_id": str(view.blob_id),
        },
    )
    result = handler.run(parse_job, _Context())
    activated = PgSourceCatalog(engine).activate(view.source_id, actor)

    # Then
    assert created is True
    assert result.result_ref is not None
    assert activated is True
    row = db.conn.execute(
        "SELECT sv.status, s.availability, cd.active, cn.text_content "
        "FROM source_versions sv "
        "JOIN sources s ON s.id = sv.source_id "
        "JOIN canonical_documents cd ON cd.source_version_id = sv.id "
        "JOIN canonical_nodes cn ON cn.canonical_document_id = cd.id "
        "WHERE sv.id = %s AND cn.text_content IS NOT NULL",
        (view.source_version_id,),
    ).fetchone()
    assert row == ("active", "active", True, PDF_TEXT)
    db.conn.close()
    engine.dispose()
