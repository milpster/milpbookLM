"""
Credential encryption ports + the versioned master-keyring value object (ch17/19).

The application owns the *contracts* and the pure keyring value; the adapters
implement the mechanism. The cipher binds owner/scope/provider into the AAD so a
ciphertext cannot be replayed against a different owner, scope or provider.
Plaintext crosses the :class:`CredentialStore.dispatch` method only - that is the
single "dispatching adapter" boundary; every other value object here is opaque
(ciphertext metadata / references, never a secret).

Master keys are parsed from a protected configuration source (never the database
or logs) and are fail-closed: a missing file, malformed key, wrong size, unknown
key id, or unknown active key id raises :class:`KeyringError` and the process
refuses to dispatch.
"""

from __future__ import annotations

import base64
import binascii
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

KEY_BYTES = 32  # XChaCha20-Poly1305 key size (libsodium crypto_aead).
NONCE_BYTES = 24  # XChaCha20-Poly1305 nonce size.


class KeyringError(ValueError):
    """The master-keyring is missing, malformed, or a required key id is unknown."""


class CredentialKeyMissingError(KeyringError):
    """A record's key id is not present in the keyring (fail closed; ciphertext untouched)."""


class CredentialDecryptionError(RuntimeError):
    """AEAD authentication failed (tampered ciphertext, nonce, AAD, or wrong key)."""


@dataclass(frozen=True, slots=True)
class MasterKeyring:
    """A versioned installation master-keyring (keys keyed by their versioned id)."""

    active_key_id: str
    _keys: Mapping[str, bytes]

    def key(self, key_id: str) -> bytes:
        """Return the 32-byte key for ``key_id``; raise CredentialKeyMissingError if absent."""
        key = self._keys.get(key_id)
        if key is None:
            raise CredentialKeyMissingError(f"master key id {key_id!r} is not in the keyring")
        return key

    def key_ids(self) -> tuple[str, ...]:
        """Return every versioned key id present (sorted for stable reports)."""
        return tuple(sorted(self._keys))

    def has(self, key_id: str) -> bool:
        """Return True when the key id is present in the keyring."""
        return key_id in self._keys


def parse_keyring(raw: Mapping[str, object]) -> MasterKeyring:
    """
    Parse a keyring mapping into a typed, fail-closed :class:`MasterKeyring`.

    Expected shape: ``{"active_key_id": <str>, "keys": {<key_id>: <b64 32 bytes>}}``.
    Raises :class:`KeyringError` on any structural/size/active-id problem.
    """
    active_raw = raw.get("active_key_id")
    keys_raw = raw.get("keys")
    if not isinstance(active_raw, str) or not active_raw:
        raise KeyringError("keyring 'active_key_id' must be a non-empty string")
    if not isinstance(keys_raw, Mapping) or not keys_raw:
        raise KeyringError("keyring 'keys' must be a non-empty mapping")
    keys: dict[str, bytes] = {}
    for key_id, value in keys_raw.items():
        if not isinstance(key_id, str) or not key_id:
            raise KeyringError("keyring key ids must be non-empty strings")
        if not isinstance(value, str):
            raise KeyringError(f"keyring key {key_id!r} must be a base64 string")
        try:
            key_bytes = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise KeyringError(f"keyring key {key_id!r} is not valid base64") from exc
        if len(key_bytes) != KEY_BYTES:
            raise KeyringError(
                f"keyring key {key_id!r} must be {KEY_BYTES} bytes, got {len(key_bytes)}"
            )
        keys[key_id] = key_bytes
    if active_raw not in keys:
        raise KeyringError(f"keyring active_key_id {active_raw!r} is not among the defined keys")
    return MasterKeyring(active_key_id=active_raw, _keys=keys)


def credential_aad(
    *, owner_user_id: uuid.UUID | None, scope: str, provider_config_id: uuid.UUID
) -> bytes:
    """
    Build the associated-data binding for one credential record.

    The AAD canonically encodes owner / scope / provider so a ciphertext is
    authenticated to exactly that (owner, scope, provider) triple and cannot be
    replayed against any other. ``owner_user_id`` of None (installation-level) is
    encoded as ``"-"``.
    """
    owner = str(owner_user_id) if owner_user_id is not None else "-"
    return f"{owner}|{scope}|{provider_config_id}".encode()


@dataclass(frozen=True, slots=True)
class CredentialRef:
    """An opaque credential reference (ciphertext metadata only; never plaintext)."""

    id: uuid.UUID
    provider_config_id: uuid.UUID
    owner_user_id: uuid.UUID | None
    credential_kind: str
    key_id: str


class CredentialCipher(Protocol):
    """AEAD credential encryption (implemented by the libsodium adapter)."""

    @property
    def active_key_id(self) -> str:
        """The key id new records are encrypted under."""
        ...

    def encrypt(self, plaintext: bytes, *, aad: bytes) -> tuple[bytes, bytes, str]:
        """
        Encrypt under the ACTIVE key; return (ciphertext, fresh nonce, active key id).

        A fresh random nonce is generated per record (never reused under a key).
        """
        ...

    def decrypt(self, ciphertext: bytes, *, nonce: bytes, key_id: str, aad: bytes) -> bytes:
        """
        Decrypt with the named key id + AAD; return plaintext.

        Raises CredentialKeyMissingError for an unknown key id (fail closed) and
        CredentialDecryptionError on AEAD authentication failure.
        """
        ...


@dataclass(frozen=True, slots=True)
class RotationReport:
    """The outcome of one rotation pass (bounded, resumable, verify-before-retire)."""

    rotated: int
    remaining: int
    verified: bool
    old_key_ids: tuple[str, ...]

    @property
    def old_key_retirement_safe(self) -> bool:
        """True only when every record is on the active key AND verified decryptable."""
        return self.verified and self.remaining == 0 and not self.old_key_ids


class CredentialStore(Protocol):
    """
    Durable provider-credential persistence + dispatch (ch17 "Credentials").

    ``dispatch`` is the single boundary that returns plaintext; everything else
    returns opaque references/metadata. Rotation is transactional and resumable in
    bounded batches and verifies before allowing old-key retirement.
    """

    def store(
        self,
        *,
        provider_config_id: uuid.UUID,
        owner_user_id: uuid.UUID | None,
        credential_kind: str,
        plaintext: bytes,
    ) -> CredentialRef:
        """Encrypt with the active key and persist; return the opaque reference."""
        ...

    def dispatch(self, ref: CredentialRef) -> bytes:
        """Load the record and decrypt it (the ONLY plaintext-returning path)."""
        ...

    def rotate_to_active(self, *, batch_size: int) -> RotationReport:
        """
        Re-encrypt every non-active record under the active key, in bounded batches.

        Resumable/idempotent (records already on the active key are skipped). After
        the pass, verifies every record decrypts; the report flags whether old-key
        retirement is safe. Aborts safely (leaving ciphertext untouched) if a record
        cannot be decrypted with its named key.
        """
        ...
