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

    # Notebook lifecycle (implemented: UI-01 creation route).
    NOTEBOOK_CREATED = "notebook.created"

    # Export (implemented: STD-01 two-stage artifact export revalidation).
    EXPORT_INITIATED = "export.initiated"

    # Studio artifacts (STD-01: lifecycle publication, export denial, study snapshots).
    ARTIFACT_CREATED = "artifact.created"
    ARTIFACT_VERSION_PUBLISHED = "artifact.version_published"
    ARTIFACT_EXPORT_DENIED = "artifact.export_denied"
    STUDY_SNAPSHOT_CREATED = "study.snapshot_created"

    # Seams for later features (named, not yet emitted by any code path):
    # membership/shared-link changes, purge, and consequential tool actions.
    MEMBERSHIP_CHANGED = "membership.changed"
    PURGE_INITIATED = "purge.initiated"
    TOOL_INVOKED = "tool.invoked"
    # RSR-01b: server-side research tool denial (the prompt-injection log).
    TOOL_DENIED = "tool.denied"

    ACQUISITION_SUCCEEDED = "source.acquisition.succeeded"
    ACQUISITION_REJECTED = "source.acquisition.rejected"
    SOURCE_ACTIVATED = "source.activated"
    SOURCE_SELECTED = "source.selected"
    SOURCE_REMOVED = "source.removed"
    SOURCE_RENAMED = "source.renamed"
