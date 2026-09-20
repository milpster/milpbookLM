"""
Initiating-actor context for background jobs.

A job acts as the user who initiated it - never as a service account (ch17). Task 5
consumes this type.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InitiatingActor:
    """
    The user who initiated a background job, plus the request that initiated it.

    Persistence: job records store user_id + request_id + trace_id verbatim;
    job handlers resolve the user through the same repository the request path
    uses and decide with the same policy engine.
    """

    user_id: uuid.UUID
    request_id: str | None = None
    trace_id: str | None = None
