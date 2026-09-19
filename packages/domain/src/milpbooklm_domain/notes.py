"""
Note / NoteRevision invariants (ch05 §7, ARCH-05-007..011).

Note is the stable collaborative object (mutable); NoteRevision is an immutable content
snapshot. A note selected as generation context MUST resolve to an immutable NoteRevision
before the operation begins. Notes never silently join the ordinary source corpus; derived
revisions retain exact content dependencies so purge traversal stays enforceable.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from enum import StrEnum


class NoteKind(StrEnum):
    """user-authored, saved chat response, or source-derived (ch05 §7)."""

    USER = "user"
    SAVED_CHAT_RESPONSE = "saved_chat_response"
    DERIVED_FROM_SOURCE = "derived_from_source"


class ContentKind(StrEnum):
    """Kinds of content a revision/manifest may depend on (purge closure + manifest pins)."""

    SOURCE_VERSION = "source_version"
    CANONICAL_DOCUMENT = "canonical_document"
    NOTE_REVISION = "note_revision"
    ARTIFACT_VERSION = "artifact_version"
    STUDY_SESSION_SNAPSHOT = "study_session_snapshot"
    MESSAGE = "message"
    EVIDENCE_SNAPSHOT = "evidence_snapshot"


@dataclass(frozen=True, slots=True)
class ContentRef:
    """A version-pinned reference to exactly one content object."""

    kind: ContentKind
    id: uuid.UUID


@dataclass(frozen=True, slots=True)
class NoteRevision:
    """Immutable snapshot of a note's content (rich structure as a JSON-ready mapping)."""

    id: uuid.UUID
    note_id: uuid.UUID
    revision_number: int
    content: dict[str, object]
    content_sha256: str
    author_user_id: uuid.UUID
    content_dependencies: tuple[ContentRef, ...] = ()


@dataclass(frozen=True, slots=True)
class Note:
    """Stable collaborative object; editability is a policy on the note (ARCH-05-007)."""

    id: uuid.UUID
    notebook_id: uuid.UUID
    kind: NoteKind
    editable: bool
    title: str
    current_revision_id: uuid.UUID | None
    revisions: tuple[NoteRevision, ...] = ()


def revision_content_sha256(content: dict[str, object]) -> str:
    """Canonical-content digest: stable under key order, exact under any change."""
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def make_revision(
    *, id: uuid.UUID, note_id: uuid.UUID, revision_number: int, content: dict[str, object],
    author_user_id: uuid.UUID, content_dependencies: tuple[ContentRef, ...] = (),
) -> NoteRevision:
    """Build a revision with its content hash; derived revisions must carry dependencies."""
    return NoteRevision(
        id=id,
        note_id=note_id,
        revision_number=revision_number,
        content=content,
        content_sha256=revision_content_sha256(content),
        author_user_id=author_user_id,
        content_dependencies=content_dependencies,
    )


def resolve_generation_context(
    note: Note, selected_revision_id: uuid.UUID
) -> NoteRevision | None:
    """
    Resolve the generation context to an immutable NoteRevision (ARCH-05-008).

    The resolved snapshot is unaffected by any later note edit.
    """
    for revision in note.revisions:
        if revision.id == selected_revision_id:
            return revision
    return None


def ordinary_source_corpus_note_ids(notebook_notes: tuple[Note, ...]) -> frozenset[uuid.UUID]:
    """
    Return the note ids eligible for the ordinary source corpus (ARCH-05-011).

    Notes NEVER silently join the corpus: no note-derived ids are included by default.
    """
    return frozenset()


def is_purge_eligible(revision: NoteRevision) -> bool:
    """
    Check whether a revision is eligible for purge traversal.

    Source-derived revisions with exact content dependencies are purge-traversable
    (ARCH-05-010 / AD-016).
    """
    return len(revision.content_dependencies) > 0
