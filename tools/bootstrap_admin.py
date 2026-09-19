"""
One-time installation administrator bootstrap CLI.

ch17: no universal/default password; the bootstrap window closes as soon as any
account exists.

Usage:
    MILPBOOKLM_BOOTSTRAP_PASSWORD=... uv run python tools/bootstrap_admin.py \
        --email admin@example.com --display-name "Installation Admin"

The DSN defaults to MILPBOOKLM_APP_DSN (the DML-only application role).
"""

from __future__ import annotations

import argparse
import os
import sys

from milpbooklm_adapters.db.connections import make_engine
from milpbooklm_adapters.security.argon2 import Argon2PasswordHasher
from milpbooklm_adapters.security.pg_identity import PgAuditLog, PgUserRepository
from milpbooklm_application.authn import BootstrapAdmin, BootstrapError, RegistrationError

ENV_PASSWORD = "MILPBOOKLM_BOOTSTRAP_PASSWORD"
ENV_DSN = "MILPBOOKLM_APP_DSN"


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser (the password never appears on the command line)."""
    parser = argparse.ArgumentParser(
        prog="bootstrap_admin",
        description="Create the one-time installation administrator (pristine installation only).",
    )
    parser.add_argument("--email", required=True, help="administrator account email")
    parser.add_argument("--display-name", required=True, help="administrator display name")
    parser.add_argument(
        "--dsn",
        default=os.environ.get(ENV_DSN, ""),
        help=f"application-role DSN (default: {ENV_DSN})",
    )
    return parser


def main(argv: list[str]) -> int:
    """Run the one-time bootstrap; returns the process exit code."""
    args = build_parser().parse_args(argv)
    password = os.environ.get(ENV_PASSWORD, "")
    if not password:
        print(f"error: {ENV_PASSWORD} must be set (no default password exists)", file=sys.stderr)
        return 2
    if not args.dsn:
        print(f"error: {ENV_DSN} (or --dsn) must be set", file=sys.stderr)
        return 2
    engine = make_engine(args.dsn)
    users = PgUserRepository(engine)
    audit = PgAuditLog(engine)
    bootstrap = BootstrapAdmin(users, Argon2PasswordHasher())
    try:
        user_id = bootstrap(args.email, args.display_name, password)
    except BootstrapError as exc:
        print(f"bootstrap refused: {exc}", file=sys.stderr)
        return 1
    except RegistrationError as exc:
        print(f"bootstrap refused: {exc}", file=sys.stderr)
        return 2
    audit.record(
        actor_id=user_id,
        action="installation.admin_bootstrapped",
        subject_kind="user",
        subject_id=user_id,
        details={"via": "bootstrap_cli"},
    )
    print(f"bootstrap complete: installation administrator {args.email!r} created ({user_id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
