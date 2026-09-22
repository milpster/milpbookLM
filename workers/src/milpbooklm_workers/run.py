"""
Worker process CLI (ch15, FND-05): ``python -m milpbooklm_workers``.

Wires the durable job surface over PostgreSQL (same adapters as the API) and runs
the poll-claim-run-publish loop until SIGINT/SIGTERM. The DSN comes from
``--dsn`` or ``MILPBOOKLM_WORKER_DSN``; the app role is DML-only, which is all a
worker needs (claim/heartbeat/terminal writes + outbox).

FND-06 maintenance commands (``--command``): the blob surface's durable entry
points - a non-destructive reconciliation scan (``reconcile``), an explicit GC
pass (``gc``), and put/get of one blob through the real store. With ``--blob-root``
set, the loop mode additionally drains the ``blob.integrity_scan`` job kind.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import signal
import uuid
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import httpx
import sqlalchemy as sa
from milpbooklm_adapters.blobs import FilesystemBlobStore, PgBlobRepository
from milpbooklm_adapters.db.connections import make_engine
from milpbooklm_adapters.fetch import HardenedFetchService
from milpbooklm_adapters.indexing import (
    PgCanonicalDocumentReader,
    PgChunkStore,
    PgGenerationStore,
    PgRetrievalService,
)
from milpbooklm_adapters.jobs import (
    PgJobRepository,
    PgOutboxDispatcher,
    PolicyAuthzRevalidator,
)
from milpbooklm_adapters.models.embedding_client import LlamaCppEmbeddingClient
from milpbooklm_adapters.parsers.isolation import IsolatedParser
from milpbooklm_adapters.parsers.pg_canonical import PgCanonicalRepository
from milpbooklm_adapters.research import (
    FAKE_SEARCH_RESULTS,
    BrowserWorkerConfig,
    FakeResearchWeb,
    PlaywrightBrowserSession,
    UnavailableBrowserSession,
)
from milpbooklm_adapters.research_runs import PgResearchRunStore
from milpbooklm_adapters.searxng.fake import FakeSearxng
from milpbooklm_adapters.searxng.service import SearxngSearchService
from milpbooklm_adapters.security.clock import SystemClock
from milpbooklm_adapters.security.notebook_reader import PgNotebookReader
from milpbooklm_adapters.security.pg_identity import PgAuditLog, PgUserRepository
from milpbooklm_adapters.sources import (
    FilesystemQuarantineStore,
    PgSourceCatalog,
    PgSourcePurge,
)
from milpbooklm_application.blob_usecases import BlobPorts, CollectBlobGarbage, ReconcileBlobs
from milpbooklm_application.indexing import (
    DEFAULT_EMBEDDING_BATCH_SIZE,
    DEFAULT_EMBEDDING_NORMALIZATION,
    BuildSourceIndex,
    EmbeddingSpec,
    IndexBuildConfig,
    config_to_payload,
    generation_id_for,
    idempotency_key_for,
)
from milpbooklm_application.job_actor import InitiatingActor
from milpbooklm_application.job_capacity import load_capacity_policy
from milpbooklm_application.job_usecases import (
    CancelJob,
    CompleteJob,
    EnqueueJob,
    JobPorts,
    RecoverExpiredLeases,
)
from milpbooklm_application.policy_engine import PolicyEngine
from milpbooklm_application.research_browser import BrowserSessionPort
from milpbooklm_application.research_executor import (
    IngestingSourceImport,
    ResearchRunExecutor,
    SourceImportPort,
)
from milpbooklm_application.research_planner import SourceDiscoveryPlanner
from milpbooklm_application.retrieval import RetrieveChunks
from milpbooklm_application.source_acquisition import AcquireSource
from milpbooklm_application.source_lifecycle import NoOpBackupExpiryScheduler
from milpbooklm_application.structured_logging import configure_structured_logging
from milpbooklm_application.web_fetch import AcquireWebSource
from milpbooklm_application.web_search_cache import CachedWebSearch
from milpbooklm_domain.blobs import MAX_BACKUP_WINDOW, gc_safety_delay_valid
from milpbooklm_domain.indexing import STRUCTURAL_CHUNKER_V1
from milpbooklm_domain.jobs import CapacityClass
from milpbooklm_domain.research import RunMode

from milpbooklm_workers import credential_cli
from milpbooklm_workers.handlers import (
    BlobIntegrityScanHandler,
    DemoEchoHandler,
    JobHandler,
    SourceParseHandler,
    SourcePurgeEraseHandler,
)
from milpbooklm_workers.indexing_handler import SourceIndexHandler
from milpbooklm_workers.loop import WorkerLoop
from milpbooklm_workers.research_handler import ResearchRunHandler, ResearchSession

ENV_WORKER_DSN = "MILPBOOKLM_WORKER_DSN"
ENV_WORKER_ID = "MILPBOOKLM_WORKER_ID"
ENV_BLOB_ROOT = "MILPBOOKLM_BLOB_ROOT"
ENV_EMBEDDING_BASE_URL = "MILPBOOKLM_EMBEDDING_BASE_URL"
ENV_EMBEDDING_MODEL = "MILPBOOKLM_EMBEDDING_MODEL"
ENV_EMBEDDING_DIMENSION = "MILPBOOKLM_EMBEDDING_DIMENSION"
ENV_SEARXNG_URL = "MILPBOOKLM_SEARXNG_URL"
ENV_RESEARCH_FAKE_WEB = "MILPBOOKLM_RESEARCH_FAKE_WEB"
ENV_RESEARCH_BROWSER = "MILPBOOKLM_RESEARCH_BROWSER"
ENV_BROWSER_PLAYWRIGHT_ROOT = "MILPBOOKLM_BROWSER_PLAYWRIGHT_ROOT"

# ch21: the GC safety delay must outlive the maximum backup-copy window (24h RPO);
# 48h is the default with one full backup cycle of headroom.
DEFAULT_GC_SAFETY_DELAY_HOURS = 48.0

CREDENTIAL_COMMANDS = (
    "store-credential",
    "dispatch-credential",
    "rotate-credentials",
    "log-canary",
)

COMMANDS = (
    "loop",
    "reconcile",
    "put-blob",
    "get-blob",
    "gc",
    "rebuild-index",
    *CREDENTIAL_COMMANDS,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the worker command line (defaults suit a single-node QA/dev deployment)."""
    parser = argparse.ArgumentParser(
        prog="milpbooklm_workers",
        description="Durable job worker: recover, claim, execute, complete (ch15).",
    )
    parser.add_argument(
        "--command",
        choices=COMMANDS,
        default="loop",
        help="loop (default) or a one-shot blob maintenance command (FND-06)",
    )
    parser.add_argument(
        "--dsn",
        default=os.environ.get(ENV_WORKER_DSN, "").strip() or None,
        help=f"PostgreSQL app-role DSN (default: ${ENV_WORKER_DSN})",
    )
    parser.add_argument(
        "--worker-id",
        default=os.environ.get(ENV_WORKER_ID, "").strip() or None,
        help=f"durable lease identity (default: ${ENV_WORKER_ID}, then pid-derived)",
    )
    parser.add_argument(
        "--queues",
        nargs="+",
        default=[c.value for c in CapacityClass],
        help="capacity classes this worker drains (default: all five)",
    )
    parser.add_argument(
        "--lease-seconds", type=int, default=10, help="claim lease length (default 10)"
    )
    parser.add_argument(
        "--poll-seconds", type=float, default=0.5, help="idle poll interval (default 0.5)"
    )
    parser.add_argument(
        "--blob-root",
        default=os.environ.get(ENV_BLOB_ROOT, "").strip() or None,
        help=f"blob store root (default: ${ENV_BLOB_ROOT}); enables blob wiring",
    )
    parser.add_argument(
        "--embedding-base-url",
        default=os.environ.get(ENV_EMBEDDING_BASE_URL, "").strip() or None,
        help=(
            "local llama.cpp embedding server root; enables the ingestion.index handler "
            f"(default: ${ENV_EMBEDDING_BASE_URL})"
        ),
    )
    parser.add_argument(
        "--embedding-model",
        default=os.environ.get(ENV_EMBEDDING_MODEL, "").strip() or "bge-m3",
        help="embedding model name recorded on generations (default: bge-m3)",
    )
    parser.add_argument(
        "--embedding-dimension",
        type=int,
        default=int(os.environ.get(ENV_EMBEDDING_DIMENSION, "").strip() or 1024),
        help="embedding dimension recorded on generations (default: 1024)",
    )
    parser.add_argument(
        "--embedding-batch",
        type=int,
        default=DEFAULT_EMBEDDING_BATCH_SIZE,
        help="texts per embedding batch (default 32)",
    )
    parser.add_argument(
        "--searxng-url",
        default=os.environ.get(ENV_SEARXNG_URL, "").strip() or None,
        help=(
            f"SearXNG instance root for the research web.search tool (default: ${ENV_SEARXNG_URL})"
        ),
    )
    parser.add_argument(
        "--research-fake-web",
        default=os.environ.get(ENV_RESEARCH_FAKE_WEB, "").strip() or None,
        metavar="{0,1}",
        help=(
            "force the deterministic fake web for research tools (QA default when "
            f"no SearXNG URL is configured; ${ENV_RESEARCH_FAKE_WEB}=0|1)"
        ),
    )
    parser.add_argument(
        "--research-browser",
        default=os.environ.get(ENV_RESEARCH_BROWSER, "").strip() or "off",
        metavar="{off,on}",
        help=(
            "enable the sandboxed Playwright browser worker for research browser "
            "tools (default off = honest typed refusals; the automation gate in "
            "the executor still applies)"
        ),
    )
    parser.add_argument(
        "--browser-playwright-root",
        default=os.environ.get(ENV_BROWSER_PLAYWRIGHT_ROOT, "").strip() or None,
        help="directory whose node_modules contains playwright for the browser worker",
    )
    parser.add_argument(
        "--browser-quarantine-dir",
        default=None,
        help="browser download quarantine directory (default: <blob-root>/quarantine/browser)",
    )
    parser.add_argument(
        "--browser-allowed-origin",
        action="append",
        default=[],
        metavar="ORIGIN",
        help=(
            "explicitly allow ONE http(s) origin for browser navigation (repeatable; "
            "default: none — loopback/private stays blocked, tests use this for fixtures)"
        ),
    )
    parser.add_argument("--source-id", default=None, help="rebuild-index: the source id (uuid)")
    parser.add_argument(
        "--gc-safety-delay-hours",
        type=float,
        default=DEFAULT_GC_SAFETY_DELAY_HOURS,
        help=(
            "GC safety delay in hours; must be > the max backup window (24h, ch21); "
            f"default {DEFAULT_GC_SAFETY_DELAY_HOURS}"
        ),
    )
    parser.add_argument("--file", default=None, help="put-blob: the file whose bytes are stored")
    parser.add_argument("--content-type", default=None, help="put-blob: optional content type")
    parser.add_argument("--referrer-kind", default=None, help="put-blob: reference referrer kind")
    parser.add_argument("--referrer-id", default=None, help="put-blob: reference referrer id")
    parser.add_argument("--blob-id", default=None, help="get-blob: the blob id to read (uuid)")
    parser.add_argument("--out", default=None, help="get-blob: write the bytes to this file")
    parser.add_argument(
        "--keyring", default=None, help="credential commands: protected master keyring JSON path"
    )
    parser.add_argument(
        "--provider-config",
        default=None,
        help="store-credential: the provider config id (uuid)",
    )
    parser.add_argument(
        "--credential-kind", default=None, help="store-credential: the credential kind"
    )
    parser.add_argument(
        "--secret-file",
        default=None,
        help="store-credential: file whose bytes are the secret (never argv)",
    )
    parser.add_argument(
        "--owner",
        default=None,
        help="store-credential: owning user id (uuid; omit for installation-level)",
    )
    parser.add_argument(
        "--credential-id",
        default=None,
        help="dispatch-credential: the credential record id (uuid)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="rotate-credentials: records per committed batch (default 100)",
    )
    return parser


def _index_build_config(args: argparse.Namespace) -> IndexBuildConfig:
    """Return the build config shared by loop-handler registration and rebuild-index."""
    return IndexBuildConfig(
        profile=STRUCTURAL_CHUNKER_V1,
        embedding=EmbeddingSpec(
            model=args.embedding_model,
            model_ref=args.embedding_base_url,
            dimension=args.embedding_dimension,
            normalization=DEFAULT_EMBEDDING_NORMALIZATION,
            batch_size=args.embedding_batch,
        ),
    )


def _build_source_index(
    engine: sa.engine.Engine, config: IndexBuildConfig, base_url: str
) -> BuildSourceIndex:
    """Wire the resumable build pipeline behind the ingestion.index handler."""
    return BuildSourceIndex(
        generations=PgGenerationStore(engine),
        chunks=PgChunkStore(engine),
        documents=PgCanonicalDocumentReader(engine),
        embeddings=LlamaCppEmbeddingClient(base_url, config.embedding.model),
    )


def _gc_safety_delay(args: argparse.Namespace) -> timedelta:
    """Parse + validate the GC safety delay (ONE policy for finals AND temp sweeps)."""
    delay = timedelta(hours=args.gc_safety_delay_hours)
    if not gc_safety_delay_valid(delay):
        window_hours = MAX_BACKUP_WINDOW.total_seconds() / 3600
        raise SystemExit(
            f"error: --gc-safety-delay-hours must be > {window_hours:g} "
            f"(the ch21 max backup-copy window); got {args.gc_safety_delay_hours}"
        )
    return delay


def _research_fake_web(args: argparse.Namespace) -> bool:
    """Resolve fake-web mode: explicit flag wins; unset defaults to fake (QA)."""
    flag = str(args.research_fake_web)
    if flag in ("0", "1"):
        return flag == "1"
    return args.searxng_url is None


def _build_research_session_factory(
    engine: sa.engine.Engine, args: argparse.Namespace
) -> Callable[[], ResearchSession]:
    """Build the per-job research session factory (fresh async services each run)."""
    blob_root = Path(args.blob_root) if args.blob_root else None

    def factory() -> ResearchSession:
        return _open_research_session(engine, args, blob_root)

    return factory


def _research_browser_session(
    args: argparse.Namespace, blob_root: Path | None
) -> BrowserSessionPort:
    """Wire the browser tool port: real sandboxed worker or honest refusal."""
    mode = str(args.research_browser)
    if mode not in ("on", "off"):
        raise SystemExit(f"error: --research-browser must be off or on: {mode}")
    if mode != "on":
        return UnavailableBrowserSession()
    quarantine_raw = str(getattr(args, "browser_quarantine_dir", "") or "")
    if quarantine_raw:
        quarantine = Path(quarantine_raw)
    elif blob_root is not None:
        quarantine = blob_root / "quarantine" / "browser"
    else:
        raise SystemExit(
            "error: --research-browser needs --browser-quarantine-dir (or --blob-root)"
        )
    return PlaywrightBrowserSession(
        BrowserWorkerConfig(
            quarantine_dir=quarantine,
            playwright_root=str(args.browser_playwright_root)
            if args.browser_playwright_root
            else None,
            allowed_origins=tuple(args.browser_allowed_origin),
        )
    )


def _open_research_session(
    engine: sa.engine.Engine, args: argparse.Namespace, blob_root: Path | None
) -> ResearchSession:
    """Open one research session: executor + per-loop service teardown."""
    fake_web = _research_fake_web(args)
    if fake_web:
        search_service = SearxngSearchService(
            transport=httpx.ASGITransport(app=FakeSearxng(results=FAKE_SEARCH_RESULTS))
        )
        fetch_service = HardenedFetchService(transport=httpx.ASGITransport(app=FakeResearchWeb()))
    elif args.searxng_url is not None:
        search_service = SearxngSearchService(base_url=args.searxng_url)
        fetch_service = HardenedFetchService()
    else:
        raise SystemExit("error: research tools need --searxng-url or fake-web mode")
    clock = SystemClock()
    audit = PgAuditLog(engine)
    jobs = _build_job_ports(engine)
    acquisition: AcquireWebSource | None = None
    if blob_root is not None:
        blob_store = FilesystemBlobStore(blob_root, PgBlobRepository(engine), clock)
        acquisition = AcquireWebSource(
            fetch=fetch_service,
            acquire=AcquireSource(
                quarantine=FilesystemQuarantineStore(blob_root, max_bytes=_max_acquisition_bytes()),
                blobs=blob_store,
                catalog=PgSourceCatalog(engine),
                audit=audit,
                jobs=jobs,
            ),
            audit=audit,
        )
    browser = _research_browser_session(args, blob_root)
    executor = ResearchRunExecutor(
        store=PgResearchRunStore(engine),
        planners={RunMode.SOURCE_DISCOVERY: SourceDiscoveryPlanner()},
        search=CachedWebSearch(
            inner=search_service, config_revision=search_service.config_revision
        ),
        fetch=fetch_service,
        browser=browser,
        imports=_require_import_port(acquisition),
        retrieval=RetrieveChunks(
            retrieval=PgRetrievalService(engine),
            embeddings=None,
            expected_dimension=None,
        ),
        audit=audit,
    )

    async def aclose() -> None:
        await search_service.aclose()
        await fetch_service.aclose()
        if isinstance(browser, PlaywrightBrowserSession):
            await browser.aclose()

    return ResearchSession(executor=executor, aclose=aclose)


def _require_import_port(acquisition: AcquireWebSource | None) -> SourceImportPort:
    """Refuse honest registration when the ingestion path is not wired."""
    if acquisition is None:
        raise SystemExit("error: research.source.import requires --blob-root (normal ingestion)")
    return IngestingSourceImport(acquisition)


def _max_acquisition_bytes() -> int:
    """Parse the shared acquisition cap (same default as the API composition)."""
    raw = os.environ.get("MILPBOOKLM_MAX_ACQUISITION_BYTES", "").strip()
    return int(raw) if raw else 10 * 1024 * 1024


def _build_job_ports(engine: sa.engine.Engine) -> JobPorts:
    """Wire the job ports over the shared adapters (worker-side instance)."""
    users = PgUserRepository(engine)
    notebooks = PgNotebookReader(engine)
    repo = PgJobRepository(engine)
    revalidator = PolicyAuthzRevalidator(engine, PolicyEngine(), users, notebooks)
    return JobPorts(
        repo=repo,
        dispatcher=PgOutboxDispatcher(engine),
        enqueue=EnqueueJob(repo, load_capacity_policy(os.environ)),
        cancel=CancelJob(repo),
        complete=CompleteJob(repo, revalidator),
        recover=RecoverExpiredLeases(repo),
    )


def build_blob_ports(
    engine: sa.engine.Engine, blob_root: Path, safety_delay: timedelta
) -> BlobPorts:
    """Wire the blob surface: filesystem store + PG bookkeeping + maintenance use cases."""
    clock = SystemClock()
    repo = PgBlobRepository(engine)
    store = FilesystemBlobStore(blob_root, repo, clock)
    return BlobPorts(
        store=store,
        repo=repo,
        reconcile=ReconcileBlobs(store, repo, clock),
        gc=CollectBlobGarbage(store, repo, clock, safety_delay),
    )


def build_worker(args: argparse.Namespace) -> WorkerLoop:
    """Wire the loop from CLI arguments (the composition seam for QA scripts)."""
    if not args.dsn:
        raise SystemExit(f"error: --dsn (or {ENV_WORKER_DSN}) is required")
    engine = make_engine(args.dsn)
    repo = PgJobRepository(engine)
    users = PgUserRepository(engine)
    notebooks = PgNotebookReader(engine)
    revalidator = PolicyAuthzRevalidator(engine, PolicyEngine(), users, notebooks)
    worker_id = args.worker_id or f"worker-{os.getpid()}"
    handlers: dict[str, JobHandler] = {DemoEchoHandler.kind: DemoEchoHandler()}
    if args.blob_root:
        blob_ports = build_blob_ports(engine, Path(args.blob_root), _gc_safety_delay(args))
        handlers[BlobIntegrityScanHandler.kind] = BlobIntegrityScanHandler(blob_ports.reconcile)
        handlers[SourceParseHandler.kind] = SourceParseHandler(
            blob_ports.store,
            IsolatedParser(),
            PgCanonicalRepository(engine),
        )
        handlers[SourcePurgeEraseHandler.kind] = SourcePurgeEraseHandler(
            PgSourcePurge(
                engine,
                NoOpBackupExpiryScheduler(),
                blob_ports.store,
            )
        )
    if args.embedding_base_url:
        config = _index_build_config(args)
        handlers[SourceIndexHandler.kind] = SourceIndexHandler(
            _build_source_index(engine, config, args.embedding_base_url)
        )
    if args.blob_root:
        handlers[ResearchRunHandler.kind] = ResearchRunHandler(
            _build_research_session_factory(engine, args)
        )
    return WorkerLoop(
        repo=repo,
        handlers=handlers,
        policy=load_capacity_policy(os.environ),
        worker_id=worker_id,
        capacity_classes=tuple(args.queues),
        lease_seconds=args.lease_seconds,
        poll_seconds=args.poll_seconds,
        complete=CompleteJob(repo, revalidator),
        recover=RecoverExpiredLeases(repo),
        cancel=CancelJob(repo),
        revalidator=revalidator,
    )


def _require(args: argparse.Namespace, *names: str) -> None:
    """Fail fast with a named usage error for a missing maintenance argument."""
    missing = [name for name in names if getattr(args, name) in (None, "")]
    if missing:
        flags = ", ".join(f"--{name.replace('_', '-')}" for name in missing)
        raise SystemExit(f"error: {flags} required for {args.command}")


def _uuid_arg(value: str | None, name: str) -> uuid.UUID:
    """Parse a required uuid CLI argument; SystemExit on a malformed value."""
    if value is None:
        raise SystemExit(f"error: --{name} is required")
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise SystemExit(f"error: --{name} is not a valid uuid: {value}") from exc


def _run_rebuild_index(args: argparse.Namespace) -> int:
    """One-shot: enqueue a resumable ingestion.index job for one activated source."""
    _require(args, "dsn", "source_id", "embedding_base_url")
    source_id = _uuid_arg(args.source_id, "source-id")
    config = _index_build_config(args)
    engine = make_engine(args.dsn)
    with engine.begin() as connection:
        row = (
            connection.execute(
                sa.text(
                    """
                SELECT s.notebook_id, s.created_by_user_id, s.current_version_id, cd.id
                FROM sources s
                LEFT JOIN canonical_documents cd
                  ON cd.source_version_id = s.current_version_id AND cd.active = true
                WHERE s.id = :source_id
                """
                ),
                {"source_id": source_id},
            )
            .mappings()
            .one()
        )
    if row["current_version_id"] is None or row["id"] is None:
        raise SystemExit("error: the source has no active canonical document to index")
    source_version_id: uuid.UUID = row["current_version_id"]
    document_id: uuid.UUID = row["id"]
    notebook_id: uuid.UUID = row["notebook_id"]
    model = config.embedding.model
    dimension = config.embedding.dimension
    generation_id = generation_id_for(source_version_id, model, dimension, config.profile.revision)
    payload: dict[str, object] = {
        "source_id": str(source_id),
        "notebook_id": str(notebook_id),
        "source_version_id": str(source_version_id),
        "canonical_document_id": str(document_id),
        "generation_id": str(generation_id),
        **config_to_payload(config),
    }
    enqueue = EnqueueJob(PgJobRepository(engine), load_capacity_policy(os.environ))
    job, created = enqueue(
        kind=SourceIndexHandler.kind,
        payload=payload,
        actor=InitiatingActor(
            user_id=row["created_by_user_id"],
            request_id=f"rebuild-index:{source_id}",
        ),
        capacity_class=CapacityClass.INGESTION_INDEXING,
        notebook_id=notebook_id,
        capability="source_mutate",
        idempotency_key=idempotency_key_for(
            source_version_id, model, dimension, config.profile.revision
        ),
    )
    print(
        json.dumps(
            {"job_id": str(job.id), "created": created, "generation_id": str(generation_id)},
            sort_keys=True,
        )
    )
    return 0


def _run_maintenance(args: argparse.Namespace) -> int:
    """One-shot blob maintenance commands (reconcile / put-blob / get-blob / gc)."""
    _require(args, "dsn", "blob_root")
    engine = make_engine(args.dsn)
    ports = build_blob_ports(engine, Path(args.blob_root), _gc_safety_delay(args))
    if args.command == "reconcile":
        report = ports.reconcile()
        print(
            json.dumps(
                {
                    "scanned_at": report.at.isoformat(),
                    "findings": [
                        {
                            "kind": finding.kind.value,
                            "blob_id": str(finding.blob_id) if finding.blob_id else None,
                            "content_sha256": finding.content_sha256,
                            "storage_path": finding.storage_path,
                            "detail": finding.detail,
                        }
                        for finding in report.findings
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "put-blob":
        _require(args, "file")
        referrer_id = _uuid_arg(args.referrer_id, "referrer-id") if args.referrer_id else None
        if (args.referrer_kind is None) != (referrer_id is None):
            raise SystemExit("error: --referrer-kind and --referrer-id must be given together")
        blob = ports.store.put(
            Path(args.file).read_bytes(),
            content_type=args.content_type,
            referrer_kind=args.referrer_kind,
            referrer_id=referrer_id,
        )
        print(
            json.dumps(
                {
                    "id": str(blob.id),
                    "content_sha256": blob.content_sha256,
                    "size_bytes": blob.size_bytes,
                    "state": blob.state.value,
                },
                sort_keys=True,
            )
        )
        return 0
    if args.command == "get-blob":
        blob_id = _uuid_arg(args.blob_id, "blob-id")
        data = ports.store.get(blob_id)
        if args.out:
            Path(args.out).write_bytes(data)
        print(
            json.dumps(
                {
                    "id": str(blob_id),
                    "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                },
                sort_keys=True,
            )
        )
        return 0
    # gc: the explicit deletion action (the safety delay is enforced by the use case).
    gc_report = ports.gc()
    print(
        json.dumps(
            {
                "at": gc_report.at.isoformat(),
                "swept_temps": gc_report.swept_temps,
                "deleted_finals": gc_report.deleted_finals,
                "pending_safety_delay": gc_report.pending_safety_delay,
                "integrity_incidents": gc_report.integrity_incidents,
            },
            sort_keys=True,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse, wire, and run the loop (or a one-shot maintenance command)."""
    args = build_parser().parse_args(argv)
    configure_structured_logging(level=logging.INFO)
    if args.command in CREDENTIAL_COMMANDS:
        return credential_cli.run(args)
    if args.command == "rebuild-index":
        return _run_rebuild_index(args)
    if args.command != "loop":
        return _run_maintenance(args)
    loop = build_worker(args)
    signal.signal(signal.SIGINT, lambda *_: loop.request_stop())
    signal.signal(signal.SIGTERM, lambda *_: loop.request_stop())
    loop.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
