"""VER-ARCH-03-004 (ARCH-03-004): long operations become durable jobs.

Oracle: the skeleton ships a durable Job value object with queue-class
grouping and a state machine, so long work is expressed as jobs (not inline
request/response).
"""

from __future__ import annotations

import uuid

from milpbooklm_workers.job import Job, JobState

from tests._evidence import REPO_ROOT, write_evidence


def test_job_is_a_durable_queued_unit() -> None:
    job = Job(id=uuid.uuid4(), queue="worker-core")
    assert job.state is JobState.QUEUED
    assert job.queue == "worker-core"


def test_job_state_machine_transitions_forward() -> None:
    job = Job(id=uuid.uuid4(), queue="worker-core")
    running = job.run()
    assert running.state is JobState.RUNNING
    assert running.id == job.id
    assert running.queue == job.queue


def test_evidence_record_written() -> None:
    write_evidence(
        "VER-ARCH-03-004",
        "ARCH-03-004",
        "tests/architecture/composition/ver-arch-03-004.py",
        {
            "job_states": [state.value for state in JobState],
            "transition": "QUEUED -> RUNNING via Job.run()",
        },
    )
    evidence = REPO_ROOT / "artifacts" / "verification" / "VER-ARCH-03-004.json"
    assert evidence.exists()
