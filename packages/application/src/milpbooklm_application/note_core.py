"""Typed application boundary for immutable notebook notes."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from milpbooklm_domain.notes import ContentRef, NoteKind

from .source_acquisition import AcquireSourceCommand, SourceView


class NoteTransformKind(StrEnum):
    """Supported transforms over explicitly selected immutable revisions."""

    COMBINE = "combine"
    CRITIQUE = "critique"
    SUMMARIZE = "summarize"
    OUTLINE = "outline"
    STUDY_GUIDE = "study_guide"
    RELATED_IDEAS = "related_ideas"


@dataclass(frozen=True, slots=True)
class NoteView:
    """Mutable logical note metadata separated from immutable content revisions."""

    note_id: uuid.UUID
    notebook_id: uuid.UUID
    kind: NoteKind
    editable: bool
    title: str
    current_revision_id: uuid.UUID | None
    created_by_user_id: uuid.UUID
    revision: int
    etag: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class NoteRevisionView:
    """One insert-only content snapshot with exact provenance dependencies."""

    revision_id: uuid.UUID
    note_id: uuid.UUID
    revision_number: int
    content: dict[str, object]
    content_sha256: str
    author_user_id: uuid.UUID
    provenance_refs: tuple[ContentRef, ...]
    content_dependencies: tuple[ContentRef, ...]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class NoteSnapshot:
    """A logical note paired with the revision made current by one command."""

    note: NoteView
    revision: NoteRevisionView


@dataclass(frozen=True, slots=True)
class SavedResponseView:
    """An actor-owned assistant response eligible for explicit note saving."""

    message_id: uuid.UUID
    content: str
    manifest_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class NotePromotionView:
    """The normal ingestion resource created from one exact note revision."""

    source_id: uuid.UUID
    source_version_id: uuid.UUID
    job_id: uuid.UUID
    created: bool


@dataclass(frozen=True, slots=True)
class CreateNoteCommand:
    """Create one editable user note and its first immutable revision."""

    actor_id: uuid.UUID
    notebook_id: uuid.UUID
    title: str
    content: dict[str, object]


@dataclass(frozen=True, slots=True)
class EditNoteCommand:
    """Append one immutable revision under logical-note ETag concurrency."""

    actor_id: uuid.UUID
    note_id: uuid.UUID
    expected_etag: str
    content: dict[str, object]


@dataclass(frozen=True, slots=True)
class SaveResponseToNoteCommand:
    """Copy one actor-owned assistant response into a non-editable note."""

    actor_id: uuid.UUID
    notebook_id: uuid.UUID
    message_id: uuid.UUID
    title: str


@dataclass(frozen=True, slots=True)
class TransformNotesCommand:
    """Transform only the explicitly selected immutable note revisions."""

    actor_id: uuid.UUID
    notebook_id: uuid.UUID
    revision_ids: tuple[uuid.UUID, ...]
    kind: NoteTransformKind
    title: str


@dataclass(frozen=True, slots=True)
class PromoteNoteCommand:
    """Promote one exact revision through normal source acquisition."""

    actor_id: uuid.UUID
    notebook_id: uuid.UUID
    revision_id: uuid.UUID
    title: str


class NoteError(Exception):
    """Base class for typed note command failures."""


class NoteConflictError(NoteError):
    """
    The submitted note ETag no longer matches the current logical note.

    Hand-written, not a frozen dataclass: the store raises it inside
    ``engine.begin()``, and contextlib assigns ``exc.__traceback__`` while the
    transaction context unwinds — a dataclass-generated frozen ``__setattr__``
    turns that into ``TypeError`` and the 409 surfaces as a 500.
    """

    __slots__ = ("note_id",)

    def __init__(self, note_id: uuid.UUID) -> None:
        """Bind the conflicted logical note identity."""
        super().__init__(note_id)
        self.note_id = note_id

    def __str__(self) -> str:
        """Return the stable optimistic-conflict description."""
        return f"note {self.note_id} changed before the edit was applied"


class NoteNotEditableError(NoteError):
    """
    The note policy forbids creating another revision.

    Same hand-written shape as ``NoteConflictError``: it must survive the
    transaction context exit where the store raises it.
    """

    __slots__ = ("note_id",)

    def __init__(self, note_id: uuid.UUID) -> None:
        """Bind the non-editable logical note identity."""
        super().__init__(note_id)
        self.note_id = note_id

    def __str__(self) -> str:
        """Return the stable editability-policy description."""
        return f"note {self.note_id} is not editable"


class NoteSelectionError(NoteError):
    """
    At least one explicitly selected revision is unavailable in the notebook.

    Same hand-written shape as ``NoteConflictError``: it must survive any
    transaction context exit where a store resolves the selection.
    """

    __slots__ = ("revision_ids",)

    def __init__(self, revision_ids: tuple[uuid.UUID, ...]) -> None:
        """Bind the exact revision identities that failed to resolve."""
        super().__init__(revision_ids)
        self.revision_ids = revision_ids

    def __str__(self) -> str:
        """Return the non-disclosing revision-selection description."""
        return "one or more selected note revisions are unavailable"


class NoteStore(Protocol):
    """Insert-only revision persistence plus mutable logical-note CAS."""

    def create(self, snapshot: NoteSnapshot) -> NoteSnapshot:
        """Persist one logical note and its first immutable revision."""
        ...

    def get_note(self, note_id: uuid.UUID) -> NoteView | None:
        """Return one logical note by identity."""
        ...

    def list_notes(self, notebook_id: uuid.UUID) -> list[NoteView]:
        """List logical notes in stable creation order."""
        ...

    def get_revision(self, revision_id: uuid.UUID) -> NoteRevisionView | None:
        """Return one immutable revision by identity."""
        ...

    def list_revisions(self, note_id: uuid.UUID) -> list[NoteRevisionView]:
        """List all retained revisions in revision order."""
        ...

    def append_revision(
        self, note_id: uuid.UUID, expected_etag: str, revision: NoteRevisionView
    ) -> NoteSnapshot | None:
        """Append under ETag concurrency and return the resulting snapshot."""
        ...

    def revisions_for_notebook(
        self, notebook_id: uuid.UUID, revision_ids: tuple[uuid.UUID, ...]
    ) -> tuple[NoteRevisionView, ...]:
        """Resolve exact selected revisions inside one notebook."""
        ...

    def saved_response(
        self, actor_id: uuid.UUID, notebook_id: uuid.UUID, message_id: uuid.UUID
    ) -> SavedResponseView | None:
        """Resolve an actor-owned private assistant response."""
        ...

    def record_promotion(
        self, note_revision_id: uuid.UUID, source_version_id: uuid.UUID
    ) -> None:
        """Persist the immutable note-to-source provenance edge."""
        ...


class NoteTransformProvider(Protocol):
    """Generate a transformed document from exact selected revisions."""

    def transform(
        self, kind: NoteTransformKind, revisions: tuple[NoteRevisionView, ...]
    ) -> dict[str, object]:
        """Return rich-note JSON for one supported transform."""
        ...


class SourceIngestion(Protocol):
    """The existing acquisition pipeline shape used by note promotion."""

    async def __call__(
        self, command: AcquireSourceCommand, chunks: AsyncIterable[bytes]
    ) -> tuple[SourceView, bool, uuid.UUID]:
        """Acquire promoted note bytes as a normal source version."""
        ...


def note_content_text(content: dict[str, object]) -> str:
    """Render rich note JSON deterministically for prompt context and ingestion."""
    return json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
