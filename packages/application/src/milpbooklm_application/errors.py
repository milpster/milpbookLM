"""
Typed identity errors shared by the use cases.

The API maps these to stable codes; no route re-derives permission logic on its own.
"""

from __future__ import annotations


class PermissionDeniedError(RuntimeError):
    """The acting user lacks the power required (e.g. not an installation administrator)."""


class AccountNotFoundError(LookupError):
    """The targeted account does not exist (raised for a known-absent id, not login)."""


class CustodyNotFoundError(LookupError):
    """The targeted notebook is not known to the custody store."""
