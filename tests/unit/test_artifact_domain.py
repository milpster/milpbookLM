"""Artifact domain invariants: the CAS transition matrix and the payload upcaster."""

from __future__ import annotations

import uuid
from itertools import product

import pytest
from milpbooklm_domain.artifacts import (
    ARTIFACT_TRANSITIONS,
    CURRENT_PAYLOAD_SCHEMA_VERSION,
    TERMINAL_ARTIFACT_STATES,
    ArtifactRequest,
    ArtifactStatus,
    ArtifactType,
    IllegalArtifactTransitionError,
    artifact_transition_allowed,
    assert_transition_allowed,
    upcast_structured_representation,
)
from milpbooklm_domain.manifests import ManifestItem
from milpbooklm_domain.notes import ContentKind

_STATES = list(ArtifactStatus)

_LEGAL_EDGES = frozenset(
    (current, target)
    for current, targets in ARTIFACT_TRANSITIONS.items()
    for target in targets
)


@pytest.mark.parametrize(("current", "target"), sorted(_LEGAL_EDGES, key=repr))
def test_legal_transitions_are_allowed(current: ArtifactStatus, target: ArtifactStatus) -> None:
    assert artifact_transition_allowed(current, target)
    assert_transition_allowed(current, target)  # must not raise


@pytest.mark.parametrize(
    ("current", "target"),
    sorted(
        {(c, t) for c, t in product(_STATES, repeat=2) if (c, t) not in _LEGAL_EDGES},
        key=repr,
    ),
)
def test_every_other_transition_is_rejected(
    current: ArtifactStatus, target: ArtifactStatus
) -> None:
    assert not artifact_transition_allowed(current, target)
    with pytest.raises(IllegalArtifactTransitionError):
        assert_transition_allowed(current, target)


def test_terminal_states_have_no_outgoing_edges() -> None:
    for state in TERMINAL_ARTIFACT_STATES:
        assert ARTIFACT_TRANSITIONS[state] == frozenset()


def test_required_lifecycle_reachable() -> None:
    """draft -> generating -> validating -> each of ready/failed/cancelled (the spec path)."""
    assert artifact_transition_allowed(ArtifactStatus.DRAFT, ArtifactStatus.GENERATING)
    assert artifact_transition_allowed(ArtifactStatus.GENERATING, ArtifactStatus.VALIDATING)
    for target in (ArtifactStatus.READY, ArtifactStatus.FAILED, ArtifactStatus.CANCELLED):
        assert artifact_transition_allowed(ArtifactStatus.VALIDATING, target)


def test_edit_and_stale_marking_edges() -> None:
    assert artifact_transition_allowed(ArtifactStatus.READY, ArtifactStatus.GENERATING)
    assert artifact_transition_allowed(ArtifactStatus.READY, ArtifactStatus.OUT_OF_DATE)
    assert artifact_transition_allowed(ArtifactStatus.OUT_OF_DATE, ArtifactStatus.GENERATING)


def test_manifest_items_order_sources_before_note_revisions() -> None:
    source_a = uuid.uuid4()
    source_b = uuid.uuid4()
    revision_a = uuid.uuid4()
    request = ArtifactRequest(
        notebook_id=uuid.uuid4(),
        artifact_type=ArtifactType.COMPOSITE,
        title="t",
        source_version_ids=(source_a, source_b),
        note_revision_ids=(revision_a,),
    )
    items = request.manifest_items()
    assert items == (
        ManifestItem(ContentKind.SOURCE_VERSION, source_a),
        ManifestItem(ContentKind.SOURCE_VERSION, source_b),
        ManifestItem(ContentKind.NOTE_REVISION, revision_a),
    )


def test_upcaster_golden_v1_to_v2() -> None:
    v1: dict[str, object] = {"schema_version": 1, "title": "Old report", "body": "flat text"}
    upcast = upcast_structured_representation(v1)
    assert upcast == {
        "schema_version": CURRENT_PAYLOAD_SCHEMA_VERSION,
        "title": "Old report",
        "sections": [{"kind": "text", "text": "flat text", "source_refs": []}],
    }


def test_upcaster_is_idempotent_at_current_version() -> None:
    v2: dict[str, object] = {
        "schema_version": CURRENT_PAYLOAD_SCHEMA_VERSION,
        "title": "t",
        "sections": [{"kind": "text", "text": "x", "source_refs": ["a"]}],
    }
    assert upcast_structured_representation(v2) is v2


def test_upcaster_rejects_unknown_schema_versions() -> None:
    with pytest.raises(ValueError, match="unknown artifact payload schema_version"):
        upcast_structured_representation({"schema_version": 99, "title": "t"})
