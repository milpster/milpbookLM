"""Refresh and privacy-purge contracts for source lifecycle operations."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class PurgePreview:
    """Identity-discovered dependent row counts shown before confirmation."""

    source_id: uuid.UUID
    counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class PurgeMark:
    """The durable purge task created by the transactional mark phase."""

    task_id: uuid.UUID
    source_id: uuid.UUID
    counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class PurgeReport:
    """Completed controlled-copy erasure report."""

    task_id: uuid.UUID
    source_id: uuid.UUID
    erased: tuple[tuple[str, int], ...]
    unresolved_external_transmission_caveat: str


class BackupExpiryScheduler(Protocol):
    """Task-50 seam for finite-retention backup expiry scheduling."""

    def schedule_source_expiry(self, source_id: uuid.UUID, purge_task_id: uuid.UUID) -> None:
        """Schedule expiry without rewriting backup generations in place."""
        ...


class NoOpBackupExpiryScheduler:
    """Default adapter until task 50 supplies backup orchestration."""

    def schedule_source_expiry(self, source_id: uuid.UUID, purge_task_id: uuid.UUID) -> None:
        """Accept the hook while active backups remain governed by retention policy."""
        del source_id, purge_task_id


class SourcePurge(Protocol):
    """Identity-based source purge with separate mark and erase phases."""

    def preview(self, source_id: uuid.UUID, actor_id: uuid.UUID) -> PurgePreview | None:
        """Return closure counts when the actor can mutate the source."""
        ...

    def mark(self, source_id: uuid.UUID, actor_id: uuid.UUID) -> PurgeMark | None:
        """Transactionally tombstone access paths and create a purge task."""
        ...

    def erase(self, task_id: uuid.UUID) -> PurgeReport:
        """Erase identity-discovered controlled copies and finish the report."""
        ...
