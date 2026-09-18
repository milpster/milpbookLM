"""Unit tests for the API composition root (use case + fake adapter wiring)."""

from __future__ import annotations

from milpbooklm_api.composition import build_create_notebook


def test_composition_round_trip() -> None:
    create_notebook, repository = build_create_notebook()
    notebook = create_notebook("Atlas")
    repository.add(notebook)
    assert repository.count() == 1
    assert repository.get(notebook.id) is not None


def test_composition_unknown_lookup_returns_none() -> None:
    from uuid import uuid4

    _, repository = build_create_notebook()
    assert repository.get(uuid4()) is None
