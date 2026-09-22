"""
Signed, nonce-bound execution-spec wire protocol (EXE-01, guide/04).

The broker accepts ONLY a signed envelope whose payload is a nonce-bound
execution specification; unsigned, tampered, stale or replayed requests are
refused with typed codes and never reach the sandbox. Signatures are
Ed25519 detached signatures over the canonical (sorted-key, compact) JSON
encoding - PyNaCl/libsodium is the installation's only cryptography
(credential_crypto precedent), and keys load only from owner-only files,
mirroring the master-keyring permission discipline.

Nonce binding: every envelope carries a fresh client-chosen nonce and
issuance timestamp; the broker rejects timestamps outside a bounded window
(stale) and any nonce seen before (replay), so a captured envelope cannot
be reused even verbatim.
"""

from __future__ import annotations

import json
import math
import os
import re
import stat
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from milpbooklm_application.execution import ExecutionRefusalCode, ExecutionRefusedError
from nacl.bindings import crypto_sign, crypto_sign_keypair, crypto_sign_open
from nacl.exceptions import BadSignatureError

PROTOCOL_VERSION: Final = 1
MAX_FRAME_BYTES: Final = 4 * 1024 * 1024
DEFAULT_NONCE_WINDOW_SECONDS: Final = 300.0
SIGNATURE_BYTES: Final = 64
_SECRET_KEY_BYTES: Final = 64
_PUBLIC_KEY_BYTES: Final = 32
_NONCE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_ENVELOPE_FIELDS: Final = frozenset({"version", "nonce", "issued_at", "spec", "signature"})


@dataclass(frozen=True, slots=True)
class SpecEnvelope:
    """The wire form: protocol version, nonce, timestamp, spec, signature."""

    version: int
    nonce: str
    issued_at: float
    spec: dict[str, object]
    signature: str | None

    def encode(self) -> bytes:
        """Canonical JSON encoding (sorted keys, compact separators)."""
        payload: dict[str, object] = {
            "version": self.version,
            "nonce": self.nonce,
            "issued_at": self.issued_at,
            "spec": self.spec,
            "signature": self.signature,
        }
        return json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()


@dataclass(frozen=True, slots=True)
class VerifiedEnvelope:
    """A verified spec paired with the nonce from its signed envelope."""

    spec: dict[str, object]
    nonce: str


def generate_signing_keypair() -> tuple[bytes, bytes]:
    """Mint one Ed25519 keypair; returns (secret_key, public_key)."""
    public_key, secret_key = crypto_sign_keypair()
    return secret_key, public_key


def sign_envelope(spec: dict[str, object], nonce: str, secret_key: bytes) -> bytes:
    """Build and sign one envelope with a fresh timestamp."""
    issued_at = time.time()
    surface = _signing_surface(PROTOCOL_VERSION, nonce, issued_at, spec)
    signature = crypto_sign(surface, secret_key)[:SIGNATURE_BYTES]
    envelope = SpecEnvelope(
        version=PROTOCOL_VERSION,
        nonce=nonce,
        issued_at=issued_at,
        spec=spec,
        signature=signature.hex(),
    )
    return envelope.encode()


class NonceReplayGuard:
    """
    Bounded in-memory nonce ledger: window + seen-set.

    Nonces are pruned by timestamp window; a replayed nonce is refused even
    when its signature still verifies (the signature proves authorship, not
    freshness). Thread-safe: the broker may serve connections from worker
    threads.
    """

    def __init__(
        self,
        *,
        window_seconds: float = DEFAULT_NONCE_WINDOW_SECONDS,
        now: Callable[[], float] = time.time,
    ) -> None:
        """Bind the freshness window (both staleness and retention)."""
        self._window = window_seconds
        self._seen: dict[str, float] = {}
        self._lock = threading.Lock()
        self._now = now

    def check_and_record(self, nonce: str, issued_at: float, *, now: float | None = None) -> None:
        """
        Accept a fresh, unseen nonce or refuse (typed).

        Raises ExecutionRefusedError with NONCE_STALE for out-of-window
        timestamps and NONCE_REPLAY for any nonce accepted before.
        """
        current = self._now() if now is None else now
        if abs(current - issued_at) > self._window:
            raise ExecutionRefusedError(
                ExecutionRefusalCode.NONCE_STALE, "nonce timestamp outside window"
            )
        with self._lock:
            self._prune(current)
            if nonce in self._seen:
                raise ExecutionRefusedError(ExecutionRefusalCode.NONCE_REPLAY, "nonce already used")
            self._seen[nonce] = issued_at

    def _prune(self, now: float) -> None:
        horizon = now - self._window
        self._seen = {nonce: seen for nonce, seen in self._seen.items() if seen >= horizon}


def verify_envelope(  # noqa: C901 - verification pipeline: one refusal branch per failure mode
    raw: bytes, public_key: bytes, replay: NonceReplayGuard
) -> VerifiedEnvelope:
    """
    Verify one raw frame and return its spec dict (typed refusals otherwise).

    Refusal codes: MALFORMED_FRAME, UNKNOWN_PROTOCOL_VERSION,
    UNSIGNED_SPEC, BAD_SIGNATURE, NONCE_STALE, NONCE_REPLAY.
    """
    try:
        payload: object = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ExecutionRefusedError(
            ExecutionRefusalCode.MALFORMED_FRAME, str(exc.__class__.__name__)
        ) from exc
    if not isinstance(payload, dict):
        raise ExecutionRefusedError(
            ExecutionRefusalCode.MALFORMED_FRAME, "frame is not a JSON object"
        )
    if set(payload) != _ENVELOPE_FIELDS:
        raise ExecutionRefusedError(
            ExecutionRefusalCode.MALFORMED_FRAME,
            "envelope fields do not match the protocol",
        )
    version = payload.get("version")
    if version != PROTOCOL_VERSION:
        raise ExecutionRefusedError(
            ExecutionRefusalCode.UNKNOWN_PROTOCOL_VERSION, f"unsupported version {version!r}"
        )
    nonce = payload.get("nonce")
    issued_at = payload.get("issued_at")
    spec = payload.get("spec")
    signature = payload.get("signature")
    if (
        not isinstance(nonce, str)
        or _NONCE.fullmatch(nonce) is None
        or isinstance(issued_at, bool)
        or not isinstance(issued_at, (int, float))
        or not math.isfinite(issued_at)
    ):
        raise ExecutionRefusedError(
            ExecutionRefusalCode.MALFORMED_FRAME, "nonce/issued_at missing or invalid"
        )
    if not isinstance(spec, dict):
        raise ExecutionRefusedError(ExecutionRefusalCode.MALFORMED_FRAME, "spec is not an object")
    if not isinstance(signature, str) or not signature:
        raise ExecutionRefusedError(
            ExecutionRefusalCode.UNSIGNED_SPEC, "envelope carries no signature"
        )
    try:
        signature_bytes = bytes.fromhex(signature)
    except ValueError as exc:
        raise ExecutionRefusedError(
            ExecutionRefusalCode.BAD_SIGNATURE, "signature is not hex"
        ) from exc
    if len(signature_bytes) != SIGNATURE_BYTES:
        raise ExecutionRefusedError(ExecutionRefusalCode.BAD_SIGNATURE, "signature length invalid")
    surface = _signing_surface(PROTOCOL_VERSION, nonce, float(issued_at), spec)
    try:
        verified = crypto_sign_open(signature_bytes + surface, public_key)
    except BadSignatureError as exc:
        raise ExecutionRefusedError(
            ExecutionRefusalCode.BAD_SIGNATURE, "signature verification failed"
        ) from exc
    if verified != surface:
        raise ExecutionRefusedError(
            ExecutionRefusalCode.BAD_SIGNATURE, "signature payload mismatch"
        )
    replay.check_and_record(nonce, float(issued_at))
    return VerifiedEnvelope(spec=spec, nonce=nonce)


def load_signing_secret(path: Path) -> bytes:
    """
    Load a 64-byte Ed25519 secret key from an owner-only file (fail closed).

    Group/other permission bits are rejected before any content is read
    (master-keyring discipline; neither key bytes nor the path appear in the
    error message).
    """
    try:
        with path.open("rb") as handle:
            if os.name == "posix":
                mode = stat.S_IMODE(os.fstat(handle.fileno()).st_mode)
                if mode & 0o077:
                    raise ExecutionRefusedError(
                        ExecutionRefusalCode.BROKER_UNAVAILABLE,
                        "signing key permissions are too broad; restrict to owner-only (chmod 600)",
                    )
            key = handle.read()
    except OSError as exc:
        raise ExecutionRefusedError(
            ExecutionRefusalCode.BROKER_UNAVAILABLE, "signing key file is unreadable"
        ) from exc
    if len(key) != _SECRET_KEY_BYTES:
        raise ExecutionRefusedError(
            ExecutionRefusalCode.BROKER_UNAVAILABLE, "signing key must be 64 bytes"
        )
    return key


def load_verification_key(path: Path) -> bytes:
    """Load a 32-byte Ed25519 public key with the same owner-only discipline."""
    try:
        with path.open("rb") as handle:
            if os.name == "posix":
                mode = stat.S_IMODE(os.fstat(handle.fileno()).st_mode)
                if mode & 0o077:
                    raise ExecutionRefusedError(
                        ExecutionRefusalCode.BROKER_UNAVAILABLE,
                        "verification key permissions are too broad;"
                        " restrict to owner-only (chmod 600)",
                    )
            key = handle.read()
    except OSError as exc:
        raise ExecutionRefusedError(
            ExecutionRefusalCode.BROKER_UNAVAILABLE, "verification key file is unreadable"
        ) from exc
    if len(key) != _PUBLIC_KEY_BYTES:
        raise ExecutionRefusedError(
            ExecutionRefusalCode.BROKER_UNAVAILABLE, "verification key must be exactly 32 bytes"
        )
    return key


def _signing_surface(version: int, nonce: str, issued_at: float, spec: dict[str, object]) -> bytes:
    payload: dict[str, object] = {
        "version": version,
        "nonce": nonce,
        "issued_at": issued_at,
        "spec": spec,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
