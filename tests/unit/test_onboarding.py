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
