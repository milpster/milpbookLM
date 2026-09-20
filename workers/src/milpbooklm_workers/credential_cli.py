"""
Credential maintenance CLI (ch17/19, FND-07): store / dispatch / rotate / canary.

Permanent operational entry points for the encrypted credential surface (same
shape as FND-06's blob commands). Plaintext only ever enters through
``--secret-file`` (never argv) and only leaves through metadata (length +
SHA-256) - dispatch output is never the secret itself. The keyring file is a
protected configuration source; a missing/unreadable keyring, a record whose
key id is absent, or any AEAD failure exits non-zero with a named error
(fail closed; the ciphertext is left untouched).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import uuid
from pathlib import Path

from milpbooklm_adapters.db.connections import make_engine
from milpbooklm_adapters.security.credential_crypto import (
    SodiumCredentialCipher,
    load_master_keyring,
)
from milpbooklm_adapters.security.pg_credentials import PgCredentialStore
from milpbooklm_application.credentials import (
    CredentialDecryptionError,
    CredentialKeyMissingError,
    CredentialRef,
    KeyringError,
)

logger = logging.getLogger(__name__)

_CANARY = "MILPBOOKLM-CANARY"


def _require(args: argparse.Namespace, *names: str) -> None:
    """Fail fast with a named usage error for a missing credential argument."""
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


def _load_store(args: argparse.Namespace) -> PgCredentialStore:
    """Wire engine + fail-closed keyring + cipher + PG store (raises KeyringError)."""
    _require(args, "dsn", "keyring")
    keyring = load_master_keyring(Path(str(args.keyring)))
    return PgCredentialStore(make_engine(str(args.dsn)), SodiumCredentialCipher(keyring))


def _store(args: argparse.Namespace) -> int:
    """Encrypt the secret-file bytes under the active key and upsert the record."""
    _require(args, "provider_config", "credential_kind", "secret_file")
    store = _load_store(args)
    ref = store.store(
        provider_config_id=_uuid_arg(str(args.provider_config), "provider-config"),
        owner_user_id=_uuid_arg(str(args.owner), "owner") if args.owner else None,
        credential_kind=str(args.credential_kind),
        plaintext=Path(str(args.secret_file)).read_bytes(),
    )
    print(json.dumps(
        {
            "id": str(ref.id),
            "provider_config_id": str(ref.provider_config_id),
            "owner_user_id": str(ref.owner_user_id) if ref.owner_user_id is not None else None,
            "credential_kind": ref.credential_kind,
            "key_id": ref.key_id,
        },
        sort_keys=True,
    ))
    return 0


def _dispatch(args: argparse.Namespace) -> int:
    """Decrypt one record and print metadata only (never the plaintext)."""
    _require(args, "credential_id")
    store = _load_store(args)
    # dispatch resolves by id (the AAD comes from the stored row fields).
    ref = CredentialRef(
        id=_uuid_arg(str(args.credential_id), "credential-id"),
        provider_config_id=uuid.UUID(int=0),
        owner_user_id=None,
        credential_kind="-",
        key_id="-",
    )
    data = store.dispatch(ref)
    print(json.dumps(
        {"id": str(ref.id), "length": len(data), "sha256": hashlib.sha256(data).hexdigest()},
        sort_keys=True,
    ))
    return 0


def _rotate(args: argparse.Namespace) -> int:
    """Run one bounded, resumable rotation pass; print the report (no secrets)."""
    store = _load_store(args)
    report = store.rotate_to_active(batch_size=int(args.batch_size))
    print(json.dumps(
        {
            "rotated": report.rotated,
            "remaining": report.remaining,
            "verified": report.verified,
            "old_key_ids": list(report.old_key_ids),
            "old_key_retirement_safe": report.old_key_retirement_safe,
        },
        sort_keys=True,
    ))
    return 0


def _log_canary(_: argparse.Namespace) -> int:
    """Emit one canary log line; the redacting formatter must scrub every value."""
    logger.warning(
        "log-canary: issued a Bearer %s-TOKEN for diagnostics",
        _CANARY,
        extra={
            "api_key": f"{_CANARY}-KEY",
            "password": f"{_CANARY}-PASS",
            "cookie": f"{_CANARY}-COOKIE",
            "authorization": f"Bearer {_CANARY}-AUTH",
        },
    )
    print(json.dumps({"canary": _CANARY}, sort_keys=True))
    return 0


def run(args: argparse.Namespace) -> int:
    """Dispatch one credential maintenance command (fail closed on key errors)."""
    try:
        if args.command == "store-credential":
            return _store(args)
        if args.command == "dispatch-credential":
            return _dispatch(args)
        if args.command == "rotate-credentials":
            return _rotate(args)
        return _log_canary(args)
    except (CredentialKeyMissingError, KeyringError, CredentialDecryptionError) as exc:
        raise SystemExit(f"error: {exc}") from exc
