"""
GenerationInputManifest invariants (ch05 §9, ARCH-05-015/016).

Every committed model-generated output pins exactly one immutable manifest. Once
materialized, the manifest never changes: later note edits, artifact revisions, preference
changes, conversation resets, connector refreshes or tool results MUST NOT silently change
it. Agent runs create NEW child manifests (parent_manifest_id) instead.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from enum import StrEnum

from .notes import ContentKind


class OperationKind(StrEnum):
    """Generation operations that must pin an immutable manifest (ARCH-05-015)."""

    ORDINARY_CHAT = "ordinary_chat"
    AGENTIC_CHAT = "agentic_chat"
    STUDIO_GENERATION = "studio_generation"
    RESEARCH_STEP = "research_step"
    NOTE_TRANSFORMATION = "note_transformation"
    STUDY_FOLLOWUP = "study_followup"


@dataclass(frozen=True, slots=True)
class ManifestItem:
    """One exact input pin: kind names the table, item_id the row, sha256 its content."""

    kind: ContentKind
    item_id: uuid.UUID
    item_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class GenerationInputManifest:
    """Immutable snapshot of the exact inputs to one generation step."""

    id: uuid.UUID
    op_kind: OperationKind
    config_snapshot: dict[str, object]
    items: tuple[ManifestItem, ...]
    parent_manifest_id: uuid.UUID | None = None
    notebook_id: uuid.UUID | None = None
    created_by_user_id: uuid.UUID | None = None


def manifest_fingerprint(manifest: GenerationInputManifest) -> str:
    """
    Compute the stable content digest of a manifest.

    Any silent change flips the fingerprint (the property-test oracle for ARCH-05-016
    stability).
    """
    payload = {
        "id": str(manifest.id),
        "op_kind": manifest.op_kind.value,
        "config": manifest.config_snapshot,
        "items": [
            {"kind": item.kind.value, "id": str(item.item_id), "sha256": item.item_sha256}
            for item in manifest.items
        ],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def can_expose_evidence(*, shared: bool, retention_policy: dict[str, object] | None) -> bool:
    """
    Decide whether run evidence may be exposed in a shared artifact.

    A shared artifact exposing run evidence needs a defined retention/share policy
    (ARCH-05-018/020); private exposure always needs none.
    """
    if not shared:
        return True
    return retention_policy is not None and len(retention_policy) > 0
