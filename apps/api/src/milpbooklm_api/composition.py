"""Composition: wire use cases to adapters (skeleton, no HTTP framework yet)."""

from __future__ import annotations

from milpbooklm_adapters.notebook_repository import InMemoryNotebookRepository
from milpbooklm_application.create_notebook import CreateNotebook


def build_create_notebook() -> tuple[CreateNotebook, InMemoryNotebookRepository]:
    """Return a ready-to-use use case and its repository (deterministic fake)."""
    repository = InMemoryNotebookRepository()
    return CreateNotebook(), repository
