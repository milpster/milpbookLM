"""Unit tests for the domain Notebook entity (pure state machine)."""

from __future__ import annotations

import uuid

from milpbooklm_domain import Notebook, NotebookStatus


def test_archive_active_returns_new_archived_notebook() -> None:
    original = Notebook(id=uuid.uuid4(), title="Atlas")
    archived = original.archive()
    assert archived.status is NotebookStatus.ARCHIVED
    assert original.status is NotebookStatus.ACTIVE
    assert archived.id == original.id


def test_archive_is_idempotent() -> None:
    archived = Notebook(id=uuid.uuid4(), title="A", status=NotebookStatus.ARCHIVED)
    assert archived.archive() is archived


def test_notebook_is_immutable() -> None:
    notebook = Notebook(id=uuid.uuid4(), title="A")
    try:
        notebook.title = "B"  # type: ignore[misc]
    except AttributeError:
        pass
    else:
        msg = "frozen dataclass accepted mutation"
        raise AssertionError(msg)
    assert notebook.title == "A"
