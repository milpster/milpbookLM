"""Cross-cutting identity contracts carried by all public commands (README engineering rules)."""

from __future__ import annotations

from typing import NewType

# All public commands carry request_id, actor_id and, where applicable,
# idempotency_key plus an authorization context.
RequestId = NewType("RequestId", str)
ActorId = NewType("ActorId", str)
IdempotencyKey = NewType("IdempotencyKey", str)

__all__ = ["ActorId", "IdempotencyKey", "RequestId"]
