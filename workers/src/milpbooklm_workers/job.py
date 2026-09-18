"""Minimal job value object. Long operations become jobs (ARCH-03-004)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum


class JobState(StrEnum):
    """Durable states of a job."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Job:
    """A durable unit of long-running work."""

    id: uuid.UUID
    queue: str
    state: JobState = JobState.QUEUED

    def run(self) -> Job:
        """Return the same job transitioned to RUNNING (immutable)."""
        return Job(id=self.id, queue=self.queue, state=JobState.RUNNING)
