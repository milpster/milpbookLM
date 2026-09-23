from __future__ import annotations

import uuid
from unittest.mock import Mock

from milpbooklm_application.note_core import NoteSnapshot, NoteStore
from milpbooklm_application.note_lifecycle import CreateNote
from milpbooklm_application.onboarding import (
    FEATURE_GUIDE_NOTES,
    FEATURE_GUIDE_TITLE,
    SeedFeatureGuide,
)
from milpbooklm_application.ports import NotebookStore, NotebookView
from milpbooklm_domain.ownership import MembershipRole


def test_seed_feature_guide_creates_owned_notebook_and_seven_revision_one_notes() -> None:
    # Given
    actor_id = uuid.uuid4()
    notebook_id = uuid.uuid4()
    notebooks = Mock(spec=NotebookStore)
    notebooks.create.return_value = NotebookView(
        notebook_id,
        FEATURE_GUIDE_TITLE,
        "none",
        MembershipRole.OWNER,
    )
    note_store = Mock(spec=NoteStore)
    created: list[NoteSnapshot] = []
    note_store.create.side_effect = lambda snapshot: created.append(snapshot) or snapshot

    # When
    SeedFeatureGuide(notebooks, CreateNote(note_store))(actor_id)

    # Then
    notebooks.create.assert_called_once_with(title=FEATURE_GUIDE_TITLE, actor_id=actor_id)
    assert [snapshot.note.title for snapshot in created] == [
        note.title for note in FEATURE_GUIDE_NOTES
    ]
    assert len(created) == len(FEATURE_GUIDE_NOTES)
    assert all(snapshot.note.editable for snapshot in created)
    assert all(snapshot.revision.revision_number == 1 for snapshot in created)
    assert all(snapshot.note.notebook_id == notebook_id for snapshot in created)


def test_feature_guide_uses_only_renderer_supported_structured_blocks() -> None:
    # Given / When
    blocks = [block for note in FEATURE_GUIDE_NOTES for block in note.content["blocks"]]

    # Then
    assert FEATURE_GUIDE_TITLE == "Welcome to milpbookLM"
    assert {block["type"] for block in blocks} == {"heading", "paragraph", "unordered_list"}
    assert all(block.get("level") in (None, 2) for block in blocks)
    assert all(
        all(isinstance(item, str) for item in block["items"])
        for block in blocks
        if block["type"] == "unordered_list"
    )
