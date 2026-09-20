"""
libsodium XChaCha20-Poly1305 credential cipher (ch17/19; PyNaCl 1.6.2 binding).

The ONLY cryptography in the installation. Encryption uses the official
XChaCha20-Poly1305 IETF AEAD binding: a 32-byte versioned master key, a fresh
random 24-byte nonce per record (CSPRNG, never reused under a key), and
associated data (owner/scope/provider) authenticated with the ciphertext.
Decryption fails closed: an unknown key id raises without touching the record;
any AEAD authentication failure (tampered bytes, nonce, AAD, or key) raises.

Master keys come from the versioned keyring parsed from a protected
configuration source - they are never persisted to the database and never
logged.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

from milpbooklm_application.credentials import (
    KEY_BYTES,
    NONCE_BYTES,
    CredentialDecryptionError,
    KeyringError,
    MasterKeyring,
    parse_keyring,
)
from nacl.bindings import randombytes
from nacl.exceptions import CryptoError
from nacl.secret import Aead


class SodiumCredentialCipher:
    """The XChaCha20-Poly1305 AEAD cipher over a versioned master-keyring."""

    def __init__(self, keyring: MasterKeyring) -> None:
        """Wire the versioned keyring (the active key encrypts, any key decrypts)."""
        self._keyring = keyring

    @property
    def active_key_id(self) -> str:
        """The key id new records are encrypted under."""
        return self._keyring.active_key_id

    def encrypt(self, plaintext: bytes, *, aad: bytes) -> tuple[bytes, bytes, str]:
        """Encrypt under the active key with a fresh random nonce; (ciphertext, nonce, key id)."""
        key_id = self._keyring.active_key_id
        key = self._keyring.key(key_id)
        nonce = randombytes(NONCE_BYTES)
        sealed = Aead(key).encrypt(plaintext, aad, nonce)
        # Aead.encrypt returns an EncryptedMessage whose bytes are nonce || ciphertext;
        # persist only the ciphertext - the nonce lives in its own column.
        ciphertext = bytes(sealed)[NONCE_BYTES:]
        return ciphertext, nonce, key_id

    def decrypt(self, ciphertext: bytes, *, nonce: bytes, key_id: str, aad: bytes) -> bytes:
        """
        Decrypt with the named key id + AAD (authenticated).

        Raises CredentialKeyMissingError (fail closed) when the key id is absent
        and CredentialDecryptionError when the AEAD check fails.
        """
        if len(nonce) != NONCE_BYTES:
            raise CredentialDecryptionError(
                f"credential nonce must be {NONCE_BYTES} bytes, got {len(nonce)}"
            )
        key = self._keyring.key(key_id)  # raises CredentialKeyMissingError if unknown
        try:
            return Aead(key).decrypt(ciphertext, aad, nonce)
        except CryptoError as exc:
            raise CredentialDecryptionError("credential AEAD authentication failed") from exc


def load_master_keyring(path: Path) -> MasterKeyring:
    """
    Parse the protected keyring file into a typed, fail-closed keyring.

    The file is a JSON document (``{"active_key_id": ..., "keys": {...}}``).
    On POSIX the opened file must be owner-only: group/other permission bits
    are rejected BEFORE any content is read. Any read/parse/validation failure
    raises :class:`KeyringError`; neither key bytes nor the file path appear in
    the error message.
    """
    try:
        with path.open(encoding="utf-8") as keyring_file:
            if os.name == "posix":
                mode = stat.S_IMODE(os.fstat(keyring_file.fileno()).st_mode)
                if mode & 0o077:
                    raise KeyringError(
                        "master keyring permissions are too broad; "
                        "restrict the file to owner-only (chmod 600)"
                    )
            raw: Any = json.load(keyring_file)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise KeyringError("master keyring file is unreadable") from exc
    if not isinstance(raw, dict):
        raise KeyringError("master keyring must be a JSON object")
    return parse_keyring(raw)


def new_key_bytes() -> bytes:
    """Mint one fresh 32-byte master key (keyring authoring helper)."""
    return randombytes(KEY_BYTES)
