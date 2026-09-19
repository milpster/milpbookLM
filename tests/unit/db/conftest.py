"""Session fixtures for the FND-03 unit database tests (real digest-pinned PG18)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from tests.domain.invariants import _pgenv


@pytest.fixture(scope="session")
def pg_env() -> Iterator[dict[str, str]]:
    """Ensure the digest-pinned PG18 is up, roles applied and migrated; yield DSNs."""
    env = _pgenv.ensure_pg()
    yield env
    _pgenv.teardown_pg()
