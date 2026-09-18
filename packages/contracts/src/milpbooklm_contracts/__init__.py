"""
Public contracts (OpenAPI, JSON Schema, event and provider descriptors).

Plain data only: no framework imports (TAD-009: OpenAPI 3.1 + versioned JSON Schema).
"""

from milpbooklm_contracts.identity import IdempotencyKey, RequestId

__all__ = ["IdempotencyKey", "RequestId"]
