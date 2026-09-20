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
from datetime import timedelta
from pathlib import Path

import sqlalchemy as sa
from milpbooklm_adapters.blobs import FilesystemBlobStore, PgBlobRepository
from milpbooklm_adapters.db.connections import make_engine
from milpbooklm_adapters.jobs import PgJobRepository, PolicyAuthzRevalidator
from milpbooklm_adapters.security.clock import SystemClock
from milpbooklm_adapters.security.notebook_reader import PgNotebookReader
from milpbooklm_adapters.security.pg_identity import PgUserRepository
from milpbooklm_application.blob_usecases import BlobPorts, CollectBlobGarbage, ReconcileBlobs
from milpbooklm_application.job_capacity import load_capacity_policy
from milpbooklm_application.job_usecases import CancelJob, CompleteJob, RecoverExpiredLeases
from milpbooklm_application.policy_engine import PolicyEngine
from milpbooklm_application.structured_logging import configure_structured_logging
from milpbooklm_domain.blobs import MAX_BACKUP_WINDOW, gc_safety_delay_valid
from milpbooklm_domain.jobs import CapacityClass

from milpbooklm_workers import credential_cli
from milpbooklm_workers.handlers import BlobIntegrityScanHandler, DemoEchoHandler, JobHandler
from milpbooklm_workers.loop import WorkerLoop

ENV_WORKER_DSN = "MILPBOOKLM_WORKER_DSN"
ENV_WORKER_ID = "MILPBOOKLM_WORKER_ID"
ENV_BLOB_ROOT = "MILPBOOKLM_BLOB_ROOT"

# ch21: the GC safety delay must outlive the maximum backup-copy window (24h RPO);
# 48h is the default with one full backup cycle of headroom.
DEFAULT_GC_SAFETY_DELAY_HOURS = 48.0

CREDENTIAL_COMMANDS = (
    "store-credential",
    "dispatch-credential",
    "rotate-credentials",
    "log-canary",
)

COMMANDS = ("loop", "reconcile", "put-blob", "get-blob", "gc", *CREDENTIAL_COMMANDS)


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


def _run_maintenance(args: argparse.Namespace) -> int:
    """One-shot blob maintenance commands (reconcile / put-blob / get-blob / gc)."""
    _require(args, "dsn", "blob_root")
    engine = make_engine(args.dsn)
    ports = build_blob_ports(engine, Path(args.blob_root), _gc_safety_delay(args))
    if args.command == "reconcile":
        report = ports.reconcile()
        print(json.dumps(
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
        ))
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
        print(json.dumps(
            {
                "id": str(blob.id),
                "content_sha256": blob.content_sha256,
                "size_bytes": blob.size_bytes,
                "state": blob.state.value,
            },
            sort_keys=True,
        ))
        return 0
    if args.command == "get-blob":
        blob_id = _uuid_arg(args.blob_id, "blob-id")
        data = ports.store.get(blob_id)
        if args.out:
            Path(args.out).write_bytes(data)
        print(json.dumps(
            {"id": str(blob_id), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()},
            sort_keys=True,
        ))
        return 0
    # gc: the explicit deletion action (the safety delay is enforced by the use case).
    gc_report = ports.gc()
    print(json.dumps(
        {
            "at": gc_report.at.isoformat(),
            "swept_temps": gc_report.swept_temps,
            "deleted_finals": gc_report.deleted_finals,
            "pending_safety_delay": gc_report.pending_safety_delay,
            "integrity_incidents": gc_report.integrity_incidents,
        },
        sort_keys=True,
    ))
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse, wire, and run the loop (or a one-shot maintenance command)."""
    args = build_parser().parse_args(argv)
    configure_structured_logging(level=logging.INFO)
    if args.command in CREDENTIAL_COMMANDS:
        return credential_cli.run(args)
    if args.command != "loop":
        return _run_maintenance(args)
    loop = build_worker(args)
    signal.signal(signal.SIGINT, lambda *_: loop.request_stop())
    signal.signal(signal.SIGTERM, lambda *_: loop.request_stop())
    loop.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
