"""Registration-only onboarding workspace seeding."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Final

from .note_core import CreateNoteCommand
from .note_lifecycle import CreateNote
from .ports import NotebookStore

FEATURE_GUIDE_TITLE: Final = "Welcome to milpbookLM"


@dataclass(frozen=True, slots=True)
class FeatureGuideNote:
    """One structured first revision in the onboarding feature guide."""

    title: str
    content: dict[str, object]


def _guide_note(
    title: str, heading: str, paragraph: str, items: tuple[str, ...]
) -> FeatureGuideNote:
    """Build one renderer-supported onboarding note."""
    return FeatureGuideNote(
        title=title,
        content={
            "blocks": [
                {"type": "heading", "level": 2, "text": heading},
                {"type": "paragraph", "text": paragraph},
                {"type": "unordered_list", "items": list(items)},
            ]
        },
    )


FEATURE_GUIDE_NOTES: Final = (
    _guide_note(
        "Start here",
        "Your private research desk",
        "milpbookLM keeps each notebook private to its members and opens it where you can work.",
        (
            "Create a notebook for one research thread.",
            "Use Notes, Sources, and Chat from its header.",
        ),
    ),
    _guide_note(
        "Sources",
        "Bring in evidence",
        "Paste text or upload supported files. Each import retains an immutable source version.",
        (
            "Select sources deliberately before asking grounded questions.",
            "Wait for terminal status.",
        ),
    ),
    _guide_note(
        "Grounded chat",
        "Ask from selected evidence",
        "Chat answers use selected source evidence and report when the material is insufficient.",
        (
            "Press Enter to send and Shift+Enter for a new line.",
            "Open available source citations.",
        ),
    ),
    _guide_note(
        "Notes",
        "Keep versioned private notes",
        "Notes are editable, immutable by revision, and visible in the Notes tab.",
        (
            "Select an exact revision before chat grounding.",
            "Unselected notes never enter a prompt.",
        ),
    ),
    _guide_note(
        "Research runs",
        "API-only preview",
        "Authenticated research-run routes expose plan, search, fetch, and import history.",
        (
            "Use the authenticated API for this provisional feature.",
            "Read-only runs do not import.",
        ),
    ),
    _guide_note(
        "Artifacts and study",
        "API-only preview",
        "Versioned artifact and private study-state APIs are implemented; their web UI is pending.",
        ("Artifact export rechecks authorization.", "More artifact families remain provisional."),
    ),
    _guide_note(
        "Privacy and capability status",
        "Know what is live",
        "Settings reports available, degraded, disabled, and provisional capabilities honestly.",
        ("Conversations are actor-private.", "Deployment health determines availability."),
    ),
)


class SeedFeatureGuide:
    """Create the private onboarding notebook through existing use cases."""

    def __init__(self, notebooks: NotebookStore, create_note: CreateNote) -> None:
        """Bind notebook persistence and the note-creation use case."""
        self._notebooks: NotebookStore = notebooks
        self._create_note: CreateNote = create_note

    def __call__(self, actor_id: uuid.UUID) -> None:
        """Create the guide notebook and its seven editable first revisions."""
        notebook = self._notebooks.create(title=FEATURE_GUIDE_TITLE, actor_id=actor_id)
        for note in FEATURE_GUIDE_NOTES:
            _ = self._create_note(
                CreateNoteCommand(
                    actor_id=actor_id,
                    notebook_id=notebook.notebook_id,
                    title=note.title,
                    content=note.content,
                )
            )
