"""
Argon2id password hashing adapter (REFERENCE-DEPENDENCIES: argon2-cffi).

Calibration is fixed at install (CalibratedParams) and the parameters are recorded
per hash in the Argon2 encoded string, so a stored hash verifies with the parameters
it was made under. check_needs_rehash flags hashes made with weaker parameters so
the login path can transparently upgrade them.
"""

from __future__ import annotations

from dataclasses import dataclass

import argon2
from argon2.exceptions import Argon2Error

# Install-time calibration (ch17: parameters recorded per hash; drift is rehashed at
# login). 64 MiB / 3 iterations / 4 lanes is a sane interactive-login default.
DEFAULT_TIME_COST = 3
DEFAULT_MEMORY_COST = 65536
DEFAULT_PARALLELISM = 4
DEFAULT_HASH_LEN = 32
DEFAULT_SALT_LEN = 16

DUMMY_CREDENTIAL = "milpbooklm-dummy-credential"


@dataclass(frozen=True, slots=True)
class CalibratedParams:
    """The install-time Argon2id calibration (recorded into every produced hash)."""

    time_cost: int = DEFAULT_TIME_COST
    memory_cost: int = DEFAULT_MEMORY_COST
    parallelism: int = DEFAULT_PARALLELISM
    hash_len: int = DEFAULT_HASH_LEN
    salt_len: int = DEFAULT_SALT_LEN


_DEFAULT_PARAMS = CalibratedParams()


class Argon2PasswordHasher:
    """Argon2id hashing implementing the application PasswordHasher port."""

    def __init__(self, params: CalibratedParams = _DEFAULT_PARAMS) -> None:
        """Build the hasher with the calibrated parameters."""
        self._params = params
        self._ph = argon2.PasswordHasher(
            time_cost=params.time_cost,
            memory_cost=params.memory_cost,
            parallelism=params.parallelism,
            hash_len=params.hash_len,
            salt_len=params.salt_len,
            type=argon2.Type.ID,
        )
        # One dummy hash computed at startup: the cost anchor for uniform login timing.
        self._dummy_hash = self._ph.hash(DUMMY_CREDENTIAL)

    @property
    def params(self) -> CalibratedParams:
        """The calibration this hasher applies to new hashes."""
        return self._params

    def hash(self, password: str) -> str:
        """Hash a plaintext password with the current calibrated parameters."""
        return self._ph.hash(password)

    def verify(self, stored_hash: str, password: str) -> bool:
        """Check a password against a stored hash (the hash carries its own params)."""
        try:
            return self._ph.verify(stored_hash, password)
        except Argon2Error:
            return False

    def needs_rehash(self, stored_hash: str) -> bool:
        """Return True when the hash was made with weaker parameters than calibration."""
        try:
            return self._ph.check_needs_rehash(stored_hash)
        except (Argon2Error, ValueError):
            return True

    def dummy_verify(self, password: str) -> bool:
        """Burn one full hash of work against the dummy (enumeration-resistance)."""
        try:
            return self._ph.verify(self._dummy_hash, password)
        except Argon2Error:
            return False
