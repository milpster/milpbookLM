"""Unit tests for the CreateNotebook use case."""

from __future__ import annotations

import pytest
from milpbooklm_application import CreateNotebook
from milpbooklm_domain import NotebookStatus


def test_create_returns_active_notebook_with_trimmed_title() -> None:
    notebook = CreateNotebook()("  Atlas  ")
    assert notebook.title == "Atlas"
    assert notebook.status is NotebookStatus.ACTIVE


def test_create_rejects_empty_title() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        CreateNotebook()("   ")
