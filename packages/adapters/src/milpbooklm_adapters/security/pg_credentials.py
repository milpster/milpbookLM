"""
PostgreSQL provider-credential store (ch17 "Credentials", FND-07).

Only ciphertext crosses this boundary: ``store`` encrypts with the active master
key (per-record random nonce, AAD bound to owner/scope/provider) and persists to
the existing ``provider_credentials`` table (encrypted_payload/key_id/nonce
columns); ``dispatch`` is the ONLY method that returns plaintext - the
"dispatching adapter" boundary. ``rotate_to_active`` re-encrypts non-active
records in bounded, committed batches (restartable and idempotent: records
already on the active key are skipped, so an interrupted rotation resumes where
it stopped) and then verifies every record decrypts before the report says
old-key retirement is safe. A missing old key fails closed and leaves the
ciphertext untouched.
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from milpbooklm_application.credentials import (
    CredentialCipher,
    CredentialDecryptionError,
    CredentialKeyMissingError,
    CredentialRef,
    RotationReport,
    credential_aad,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert

from milpbooklm_adapters.db.tables.providers import provider_credentials


def _aad_for_row(row: Any) -> bytes:
    """Rebuild the record's AAD from its authoritative stored fields."""
    return credential_aad(
        owner_user_id=row.owner_user_id,
        scope=row.credential_kind,
        provider_config_id=row.provider_config_id,
    )


class PgCredentialStore:
    """The provider_credentials table adapter implementing the CredentialStore port."""

    def __init__(self, engine: sa.engine.Engine, cipher: CredentialCipher) -> None:
        """Wire the engine and the XChaCha20-Poly1305 cipher."""
        self._engine = engine
        self._cipher = cipher

    def store(
        self,
        *,
        provider_config_id: uuid.UUID,
        owner_user_id: uuid.UUID | None,
        credential_kind: str,
        plaintext: bytes,
    ) -> CredentialRef:
        """Encrypt with the active key and upsert the record; return the opaque ref."""
        aad = credential_aad(
            owner_user_id=owner_user_id,
            scope=credential_kind,
            provider_config_id=provider_config_id,
        )
        ciphertext, nonce, key_id = self._cipher.encrypt(plaintext, aad=aad)
        # One atomic upsert: one credential per (provider, owner). The unique index is
        # NULLS NOT DISTINCT, so installation-level (NULL owner) rows conflict too.
        stmt = (
            pg_insert(provider_credentials)
            .values(
                provider_config_id=provider_config_id,
                owner_user_id=owner_user_id,
                credential_kind=credential_kind,
                encrypted_payload=ciphertext,
                key_id=key_id,
                nonce=nonce,
            )
            .on_conflict_do_update(
                index_elements=["provider_config_id", "owner_user_id"],
                set_={
                    "credential_kind": credential_kind,
                    "encrypted_payload": ciphertext,
                    "key_id": key_id,
                    "nonce": nonce,
                    "updated_at": sa.func.now(),
                },
            )
            .returning(provider_credentials.c.id)
        )
        with self._engine.begin() as conn:
            row = conn.execute(stmt).one()
        return CredentialRef(
            id=row.id,
            provider_config_id=provider_config_id,
            owner_user_id=owner_user_id,
            credential_kind=credential_kind,
            key_id=key_id,
        )

    def dispatch(self, ref: CredentialRef) -> bytes:
        """Load the record and decrypt it (the ONLY plaintext-returning path)."""
        with self._engine.begin() as conn:
            row = conn.execute(
                sa.select(provider_credentials).where(provider_credentials.c.id == ref.id)
            ).first()
        if row is None:
            msg = f"unknown credential {ref.id}"
            raise LookupError(msg)
        return self._cipher.decrypt(
            bytes(row.encrypted_payload),
            nonce=bytes(row.nonce),
            key_id=row.key_id,
            aad=_aad_for_row(row),
        )

    def rotate_to_active(self, *, batch_size: int) -> RotationReport:
        """
        Re-encrypt non-active records under the active key (bounded, resumable).

        Each batch commits, so progress is durable: an interrupted rotation resumes
        (records already on the active key are skipped). Aborts safely - propagating
        the cipher error and rolling back the in-flight batch - when a record cannot
        be decrypted with its named key. The final verification pass must pass and
        leave no non-active records before old-key retirement is safe.
        """
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        active = self._cipher.active_key_id
        rotated = 0
        while True:
            with self._engine.begin() as conn:
                rows = conn.execute(
                    sa.select(provider_credentials)
                    .where(provider_credentials.c.key_id != active)
                    .order_by(provider_credentials.c.id)
                    .limit(batch_size)
                ).fetchall()
                if not rows:
                    break
                for row in rows:
                    plaintext = self._cipher.decrypt(
                        bytes(row.encrypted_payload),
                        nonce=bytes(row.nonce),
                        key_id=row.key_id,
                        aad=_aad_for_row(row),
                    )
                    ciphertext, nonce, key_id = self._cipher.encrypt(
                        plaintext, aad=_aad_for_row(row)
                    )
                    result = conn.execute(
                        sa.update(provider_credentials)
                        .where(
                            provider_credentials.c.id == row.id,
                            provider_credentials.c.key_id == row.key_id,
                        )
                        .values(
                            encrypted_payload=ciphertext,
                            nonce=nonce,
                            key_id=key_id,
                            updated_at=sa.func.now(),
                        )
                    )
                    if result.rowcount > 0:
                        rotated += 1
            # Batch committed: durable progress (the rotation is resumable).
        remaining, verified, old_key_ids = self._verify_after_rotation(active)
        return RotationReport(
            rotated=rotated,
            remaining=remaining,
            verified=verified,
            old_key_ids=old_key_ids,
        )

    def _verify_after_rotation(
        self, active: str
    ) -> tuple[int, bool, tuple[str, ...]]:
        """Verify every record decrypts; return (remaining, verified, old key ids)."""
        remaining = 0
        old_ids: set[str] = set()
        verified = True
        with self._engine.begin() as conn:
            rows = conn.execute(sa.select(provider_credentials)).fetchall()
        for row in rows:
            if row.key_id != active:
                remaining += 1
                old_ids.add(row.key_id)
            try:
                self._cipher.decrypt(
                    bytes(row.encrypted_payload),
                    nonce=bytes(row.nonce),
                    key_id=row.key_id,
                    aad=_aad_for_row(row),
                )
            except (CredentialKeyMissingError, CredentialDecryptionError):
                verified = False
        return remaining, verified, tuple(sorted(old_ids))
