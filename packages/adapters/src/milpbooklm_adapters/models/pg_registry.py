"""PostgreSQL provider registry over FND-07 config and credential tables."""

from __future__ import annotations

import uuid
from collections.abc import Mapping

import sqlalchemy as sa
from milpbooklm_application.credentials import CredentialRef
from milpbooklm_application.models.registry import (
    CapabilityDescriptor,
    ProviderCandidate,
    ProviderRegistry,
    ProviderTrust,
)

from milpbooklm_adapters.db.tables.providers import provider_configs, provider_credentials


class PgProviderRegistry(ProviderRegistry):
    """Read installation configs separately from owner-scoped credential metadata."""

    def __init__(
        self,
        engine: sa.engine.Engine,
        descriptors: Mapping[uuid.UUID, CapabilityDescriptor],
        trust: Mapping[uuid.UUID, ProviderTrust],
    ) -> None:
        """Wire persistence and administrator-approved capability metadata."""
        self._engine = engine
        self._descriptors = descriptors
        self._trust = trust

    def candidates(self, actor_user_id: uuid.UUID) -> tuple[ProviderCandidate, ...]:
        """Return enabled configs with installation or actor-owned credential references."""
        with self._engine.begin() as conn:
            rows = conn.execute(
                sa.select(
                    provider_configs.c.id,
                    provider_configs.c.provider_kind,
                    provider_configs.c.display_name,
                    provider_configs.c.base_url,
                    provider_credentials.c.id.label("credential_id"),
                    provider_credentials.c.owner_user_id,
                    provider_credentials.c.credential_kind,
                    provider_credentials.c.key_id,
                )
                .outerjoin(
                    provider_credentials,
                    sa.and_(
                        provider_credentials.c.provider_config_id == provider_configs.c.id,
                        sa.or_(
                            provider_credentials.c.owner_user_id == actor_user_id,
                            provider_credentials.c.owner_user_id.is_(None),
                        ),
                    ),
                )
                .where(provider_configs.c.enabled.is_(True))
                .order_by(provider_credentials.c.owner_user_id.desc().nulls_last())
            ).all()
        chosen: dict[uuid.UUID, ProviderCandidate] = {}
        for row in rows:
            if row.id in chosen or row.id not in self._descriptors or row.id not in self._trust:
                continue
            credential = None
            if row.credential_id is not None:
                credential = CredentialRef(
                    id=row.credential_id,
                    provider_config_id=row.id,
                    owner_user_id=row.owner_user_id,
                    credential_kind=row.credential_kind,
                    key_id=row.key_id,
                )
            chosen[row.id] = ProviderCandidate(
                config_id=row.id,
                provider_kind=row.provider_kind,
                display_name=row.display_name,
                base_url=row.base_url or "",
                trust=self._trust[row.id],
                descriptor=self._descriptors[row.id],
                credential=credential,
            )
        return tuple(chosen.values())
