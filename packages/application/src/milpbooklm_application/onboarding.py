"""Registration-only onboarding workspace seeding."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Final

from .note_core import CreateNoteCommand
from .note_lifecycle import CreateNote
from .ports import NotebookStore

FEATURE_GUIDE_TITLE: Final = "Welcome to MilBook LM — Feature Guide"


@dataclass(frozen=True, slots=True)
class FeatureGuideNote:
    """One revision-one note in the onboarding feature guide."""

    title: str
    text: str


FEATURE_GUIDE_NOTES: Final = (
    FeatureGuideNote(
        "Start here — your private research workspace",
        "MilBook LM is local-first and private by default. Log out and back in without losing "
        + "your workspace: each notebook is privately owned by your account.",
    ),
    FeatureGuideNote(
        "Collecting sources",
        "Use the Sources tab to paste text or upload a file. Each ingestion creates an immutable "
        + "source version. Selected, successfully promoted sources feed notebook search "
        + "and grounded "
        + "chat, and persisted sources remain listed after reload or login.",
    ),
    FeatureGuideNote(
        "Grounded chat with citations",
        "Start an actor-private chat from a notebook. Answers use selected notebook sources only, "
        + "show citation chips that open the source viewer, and report when the available "
        + "evidence is "
        + "insufficient instead of inventing support.",
    ),
    FeatureGuideNote(
        "Research runs",
        "The research-run API supports visible plan, search, fetch, and import step history. Runs "
        + "with a limited tool set remain read-only and finish without importing. This "
        + "prototype does "
        + "not yet expose research runs in the web UI; use the authenticated /api/v1/research-runs "
        + "routes today.",
    ),
    FeatureGuideNote(
        "Notes — capture and transform your thinking",
        "The notes API creates editable notes as immutable revisions, supports explicit "
        + "transforms, saving a private chat response, promotion to a source, and explicit "
        + "note-revision pinning for chat. The notebook web UI does not expose notes yet; "
        + "use the authenticated notes API.",
    ),
    FeatureGuideNote(
        "Artifacts & study progress (API preview)",
        "The versioned artifact API currently supports the composite recipe, optimistic "
        + "ETag edits, "
        + "two-stage export authorization with a download recheck, and private study state. More "
        + "artifact families and their web UI are still in progress.",
    ),
    FeatureGuideNote(
        "Privacy, custody & what stays local",
        "Models and the database run locally in the documented deployment. Conversations and notes "
        + "remain private, provenance links retained material to its origins, and exports recheck "
        + "authorization at download time. Settings reports each capability as available, "
        + "degraded, "
        + "disabled, or provisional rather than presenting unfinished work as live.",
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
                    content={"blocks": [{"type": "paragraph", "text": note.text}]},
                )
            )
