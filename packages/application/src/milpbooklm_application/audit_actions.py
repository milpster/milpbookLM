"""
Typed audit action categories (ch18/ch19 "Secrets and audit").

The plan's audited action set is: login, membership/share, provider/credential,
custody/break-glass, purge, export, and consequential tool actions. Only the
actions this prototype has implemented are named here (login + the custody
actions the use cases already emit); the rest are named as *seams* so a later
feature adds its constant instead of inventing ad-hoc strings. Audit rows are
metadata-only: content never enters them.
"""

from __future__ import annotations

from enum import StrEnum


class AuditAction(StrEnum):
    """Stable, typed audit action names (the append-only trail's vocabulary)."""

    # Authentication (implemented: login/register surface).
    LOGIN_SUCCEEDED = "auth.login.succeeded"
    LOGIN_FAILED = "auth.login.failed"

    # Custody / break-glass (implemented: administrative-custody use cases).
    CUSTODY_LOCKED = "custody.locked"
    CUSTODY_TRANSFERRED = "custody.transferred"
    CUSTODY_SCHEDULED_DELETION = "custody.scheduled_deletion"

    # Provider credential lifecycle (implemented by the worker maintenance CLI).
    CREDENTIAL_STORED = "credential.stored"
    CREDENTIAL_ROTATED = "credential.rotated"

    # Seams for later features (named, not yet emitted by any code path):
    # membership/shared-link changes, purge, export, and consequential tool actions.
    MEMBERSHIP_CHANGED = "membership.changed"
    PURGE_INITIATED = "purge.initiated"
    EXPORT_INITIATED = "export.initiated"
    TOOL_INVOKED = "tool.invoked"
