"""
PostgreSQL jobs/outbox/idempotency adapters (ch15, FND-05).

Implements the application JobRepository + OutboxDispatcher ports over the T3
schema (jobs, job_attempts, outbox_events, idempotency_keys). Claiming uses
``FOR UPDATE SKIP LOCKED``; terminal publication commits atomically with its
outbox event; idempotency is a scoped unique (scope, key) with the request
hash as the conflict discriminator.
"""

from milpbooklm_adapters.jobs.pg_job_authz import PolicyAuthzRevalidator
from milpbooklm_adapters.jobs.pg_jobs import PgJobRepository
from milpbooklm_adapters.jobs.pg_outbox import PgOutboxDispatcher

__all__ = [
    "PgJobRepository",
    "PgOutboxDispatcher",
    "PolicyAuthzRevalidator",
]
