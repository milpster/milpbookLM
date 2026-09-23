"""
Studio artifact framework invariants (ch13, ARCH-13-001..014, TECH-13-001).

An artifact is the stable logical object (the mutable ``artifacts`` row); an
artifact version is its immutable content (the ``artifact_versions`` row). The
lifecycle below drives ONE generation pass over the logical artifact:

    draft -> generating -> validating -> ready | failed | cancelled

A ``ready`` artifact may start a new generation pass (edit / regeneration) and
may be marked ``out_of_date`` when a source advances. Every published version
is retained: a new version never mutates or deletes a prior one (immutability
is enforced at the schema layer, mirrored here by the transition table which
never consumes a version row).

The :class:`ArtifactRecipe` contract is the single internal extension point:
validate request -> freeze inputs (manifest) -> plan -> generate structured
content -> validate -> render optional renditions -> publish an immutable
version. Recipes register internally at startup through a typed registry; there
is no runtime code loading (guide/13 Extension).

The canonical payload is versioned JSON (``structured_representation``).
:func:`upcast_structured_representation` is the schema-evolution path: an older
payload shape is upcast to the current schema so historical versions stay
readable (guide/13 Extension "migration/upcaster and golden compatibility
tests").
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Protocol

from .manifests import ManifestItem
from .notes import ContentKind


class ArtifactType(StrEnum):
    """The Studio artifact types (ch05 artifacts.artifact_type check constraint)."""

    REPORT = "report"
    TABLE = "table"
    MIND_MAP = "mind_map"
    FLASHCARDS = "flashcards"
    QUIZ = "quiz"
    SLIDE_DECK = "slide_deck"
    INFOGRAPHIC = "infographic"
    AUDIO_OVERVIEW = "audio_overview"
    VIDEO_OVERVIEW = "video_overview"
    COMPOSITE = "composite"


class ArtifactStatus(StrEnum):
    """Durable artifact lifecycle states (one generation pass over the logical row)."""

    DRAFT = "draft"
    GENERATING = "generating"
    VALIDATING = "validating"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"
    OUT_OF_DATE = "out_of_date"


TERMINAL_ARTIFACT_STATES: frozenset[ArtifactStatus] = frozenset(
    {ArtifactStatus.FAILED, ArtifactStatus.CANCELLED}
)

# Compare-and-swap transition table: the logical artifact moves only along these
# edges. Prior ready versions are never consumed by a transition - they are
# retained as immutable rows and only ``current_version_id`` advances.
ARTIFACT_TRANSITIONS: Final[dict[ArtifactStatus, frozenset[ArtifactStatus]]] = {
    ArtifactStatus.DRAFT: frozenset({ArtifactStatus.GENERATING, ArtifactStatus.CANCELLED}),
    ArtifactStatus.GENERATING: frozenset(
        {ArtifactStatus.VALIDATING, ArtifactStatus.FAILED, ArtifactStatus.CANCELLED}
    ),
    ArtifactStatus.VALIDATING: frozenset(
        {ArtifactStatus.READY, ArtifactStatus.FAILED, ArtifactStatus.CANCELLED}
    ),
    # A ready artifact can start a new generation pass (edit/regeneration) or be
    # marked stale when a source advances (ARCH-13-010).
    ArtifactStatus.READY: frozenset({ArtifactStatus.GENERATING, ArtifactStatus.OUT_OF_DATE}),
    ArtifactStatus.OUT_OF_DATE: frozenset({ArtifactStatus.GENERATING}),
    ArtifactStatus.FAILED: frozenset(),
    ArtifactStatus.CANCELLED: frozenset(),
}


class IllegalArtifactTransitionError(ValueError):
    """An artifact transition outside the CAS table (stale writer, double-terminal)."""


def artifact_transition_allowed(current: ArtifactStatus, target: ArtifactStatus) -> bool:
    """Return True when current -> target is a legal artifact state edge."""
    return target in ARTIFACT_TRANSITIONS[current]


def assert_transition_allowed(current: ArtifactStatus, target: ArtifactStatus) -> None:
    """Raise :class:`IllegalArtifactTransitionError` for an illegal edge."""
    if not artifact_transition_allowed(current, target):
        raise IllegalArtifactTransitionError(
            f"illegal artifact transition {current.value} -> {target.value}"
        )


@dataclass(frozen=True, slots=True)
class ArtifactRequest:
    """
    A validated artifact generation request (the recipe's input contract).

    ``base_version_number`` pins the lineage for edit/regeneration: when set, the
    new manifest is a child of the base version's manifest (ARCH-13 revision
    targets a structured element; the base's exact inputs are preserved).
    """

    notebook_id: uuid.UUID
    artifact_type: ArtifactType
    title: str
    instructions: str | None = None
    source_version_ids: tuple[uuid.UUID, ...] = ()
    note_revision_ids: tuple[uuid.UUID, ...] = ()
    base_version_number: int | None = None

    def manifest_items(self) -> tuple[ManifestItem, ...]:
        """Return the exact frozen inputs this request will pin (sources + notes)."""
        items: list[ManifestItem] = [
            ManifestItem(ContentKind.SOURCE_VERSION, source_version_id)
            for source_version_id in self.source_version_ids
        ]
        items.extend(
            ManifestItem(ContentKind.NOTE_REVISION, note_revision_id)
            for note_revision_id in self.note_revision_ids
        )
        return tuple(items)


@dataclass(frozen=True, slots=True)
class FrozenInputs:
    """The immutable manifest scope handed to a recipe (guide/13 freeze step)."""

    manifest_id: uuid.UUID
    items: tuple[ManifestItem, ...]
    config_snapshot: dict[str, object]


@dataclass(frozen=True, slots=True)
class Rendition:
    """One separately-referenced rendered form (the canonical payload stays JSON)."""

    format: str
    content: bytes


class ArtifactRecipe(Protocol):
    """
    The internal artifact recipe contract (guide/13 Recipe system).

    A recipe is a versioned, deterministic pipeline over frozen inputs. It
    performs NO persistence: the framework freezes the manifest and publishes
    the immutable version; the recipe only transforms.
    """

    recipe_id: str
    recipe_version: str
    artifact_type: ArtifactType

    def validate_request(self, request: ArtifactRequest) -> None:
        """Reject a request the recipe cannot serve (raise ValueError)."""
        ...

    def plan(self, request: ArtifactRequest, inputs: FrozenInputs) -> dict[str, object]:
        """Produce the generation plan from frozen inputs (deterministic)."""
        ...

    def generate(
        self, request: ArtifactRequest, inputs: FrozenInputs, plan: dict[str, object]
    ) -> dict[str, object]:
        """Generate the structured content (the canonical versioned JSON payload)."""
        ...

    def validate_content(
        self, content: dict[str, object], inputs: FrozenInputs
    ) -> tuple[str, ...]:
        """Return validation problems (empty tuple = valid) before publication."""
        ...

    def render(self, content: dict[str, object]) -> tuple[Rendition, ...]:
        """Render optional renditions (empty when the type has none)."""
        ...


CURRENT_PAYLOAD_SCHEMA_VERSION: Final = 2
_OLDEST_PAYLOAD_SCHEMA_VERSION: Final = 1


def upcast_structured_representation(
    payload: dict[str, object],
) -> dict[str, object]:
    """
    Upcast an artifact-version payload to the current schema version.

    v1 payloads carried a single flat ``body`` string; the v2 (current) payload
    is a section list. The upcast is deterministic and idempotent: a payload
    already at the current version is returned unchanged. An unknown schema
    version is rejected (ValueError) - evolution is forward-only and explicit.
    """
    version = payload.get("schema_version")
    if version == CURRENT_PAYLOAD_SCHEMA_VERSION:
        return payload
    if version == _OLDEST_PAYLOAD_SCHEMA_VERSION:
        title = payload.get("title", "")
        body = payload.get("body", "")
        return {
            "schema_version": CURRENT_PAYLOAD_SCHEMA_VERSION,
            "title": title,
            "sections": [{"kind": "text", "text": body, "source_refs": []}],
        }
    raise ValueError(f"unknown artifact payload schema_version: {version!r}")
