"""Validated request and response shapes for note HTTP routes."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping

from milpbooklm_application.note_core import (
    NoteRevisionView,
    NoteSnapshot,
    NoteTransformKind,
    NoteView,
)
from pydantic import BaseModel, ConfigDict, Field

# Resolves user ids to display names at the HTTP boundary so note payloads
# never leak a raw uuid where a human-readable attribution is displayed.
DisplayNameResolver = Callable[[frozenset[uuid.UUID]], Mapping[uuid.UUID, str]]

UNKNOWN_AUTHOR = "unknown"


def no_display_names(_: frozenset[uuid.UUID]) -> Mapping[uuid.UUID, str]:
    """Default resolver for unwired installations: no names are known."""
    return {}


class CreateNoteRequest(BaseModel):
    """Create one editable note with its first immutable revision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    content: dict[str, object] = Field(min_length=1)


class EditNoteRequest(BaseModel):
    """Content for one append-only revision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    content: dict[str, object] = Field(min_length=1)


class SaveResponseRequest(BaseModel):
    """Explicitly copy one private assistant response into a shared immutable note."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    message_id: uuid.UUID
    title: str = Field(min_length=1, max_length=300)


class TransformNotesRequest(BaseModel):
    """Transform exact selected note revisions into a new editable note."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    revision_ids: tuple[uuid.UUID, ...] = Field(min_length=1, max_length=100)
    kind: NoteTransformKind
    title: str = Field(min_length=1, max_length=300)


class PromoteNoteRequest(BaseModel):
    """Promote one exact note revision through normal source ingestion."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str = Field(min_length=1, max_length=300)


def note_payload(note: NoteView, names: Mapping[uuid.UUID, str] | None = None) -> dict[str, object]:
    """Serialize mutable logical-note metadata without content."""
    resolved = names if names is not None else {}
    return {
        "note_id": str(note.note_id),
        "notebook_id": str(note.notebook_id),
        "kind": note.kind.value,
        "editable": note.editable,
        "title": note.title,
        "current_revision_id": (
            str(note.current_revision_id) if note.current_revision_id is not None else None
        ),
        "revision": note.revision,
        "etag": note.etag,
        "created_by_user_id": str(note.created_by_user_id),
        "created_by_name": resolved.get(note.created_by_user_id, UNKNOWN_AUTHOR),
        "created_at": note.created_at.isoformat(),
        "updated_at": note.updated_at.isoformat(),
    }


def revision_payload(
    revision: NoteRevisionView, names: Mapping[uuid.UUID, str] | None = None
) -> dict[str, object]:
    """Serialize one immutable revision and its exact dependency references."""
    resolved = names if names is not None else {}
    return {
        "revision_id": str(revision.revision_id),
        "note_id": str(revision.note_id),
        "revision_number": revision.revision_number,
        "content": revision.content,
        "content_sha256": revision.content_sha256,
        "author_user_id": str(revision.author_user_id),
        "author_name": resolved.get(revision.author_user_id, UNKNOWN_AUTHOR),
        "provenance_refs": [
            {"kind": reference.kind.value, "id": str(reference.id)}
            for reference in revision.provenance_refs
        ],
        "content_dependencies": [
            {"kind": reference.kind.value, "id": str(reference.id)}
            for reference in revision.content_dependencies
        ],
        "created_at": revision.created_at.isoformat(),
    }


def snapshot_payload(
    snapshot: NoteSnapshot, names: Mapping[uuid.UUID, str] | None = None
) -> dict[str, object]:
    """Serialize a logical note paired with its newly current revision."""
    return {
        "note": note_payload(snapshot.note, names),
        "revision": revision_payload(snapshot.revision, names),
    }
