"""
Worker process CLI (ch15, FND-05): ``python -m milpbooklm_workers``.

Wires the durable job surface over PostgreSQL (same adapters as the API) and runs
the poll-claim-run-publish loop until SIGINT/SIGTERM. The DSN comes from
``--dsn`` or ``MILPBOOKLM_WORKER_DSN``; the app role is DML-only, which is all a
worker needs (claim/heartbeat/terminal writes + outbox).
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys

from milpbooklm_adapters.db.connections import make_engine
from milpbooklm_adapters.jobs import PgJobRepository, PolicyAuthzRevalidator
from milpbooklm_adapters.security.notebook_reader import PgNotebookReader
from milpbooklm_adapters.security.pg_identity import PgUserRepository
from milpbooklm_application.job_capacity import load_capacity_policy
from milpbooklm_application.job_usecases import CancelJob, CompleteJob, RecoverExpiredLeases
from milpbooklm_application.policy_engine import PolicyEngine
from milpbooklm_domain.jobs import CapacityClass

from milpbooklm_workers.handlers import DemoEchoHandler
from milpbooklm_workers.loop import WorkerLoop

ENV_WORKER_DSN = "MILPBOOKLM_WORKER_DSN"
ENV_WORKER_ID = "MILPBOOKLM_WORKER_ID"


def build_parser() -> argparse.ArgumentParser:
    """Build the worker command line (defaults suit a single-node QA/dev deployment)."""
    parser = argparse.ArgumentParser(
        prog="milpbooklm_workers",
        description="Durable job worker: recover, claim, execute, complete (ch15).",
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
    return parser


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
    return WorkerLoop(
        repo=repo,
        handlers={DemoEchoHandler.kind: DemoEchoHandler()},
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


def main(argv: list[str] | None = None) -> int:
    """Parse, wire, and run the loop until a stop signal arrives."""
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    loop = build_worker(args)
    signal.signal(signal.SIGINT, lambda *_: loop.request_stop())
    signal.signal(signal.SIGTERM, lambda *_: loop.request_stop())
    loop.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
