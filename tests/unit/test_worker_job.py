"""Unit tests for the worker Job value object (durable job state machine)."""

from __future__ import annotations

import uuid

from milpbooklm_workers import Job, JobState


def test_job_starts_queued_in_its_queue() -> None:
    job = Job(id=uuid.uuid4(), queue="worker-core")
    assert job.state is JobState.QUEUED
    assert job.queue == "worker-core"


def test_job_runs_forward_preserving_identity() -> None:
    job = Job(id=uuid.uuid4(), queue="worker-media")
    running = job.run()
    assert running.state is JobState.RUNNING
    assert running.id == job.id
    assert running.queue == job.queue
