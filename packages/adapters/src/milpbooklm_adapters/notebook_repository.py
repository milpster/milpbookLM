"""In-memory notebook repository: a deterministic fake adapter (ARCH-03-001 fixture)."""

from __future__ import annotations

import uuid

from milpbooklm_domain.notebook import Notebook


class InMemoryNotebookRepository:
    """Stores notebooks in a dict. Satisfies the persistence port without I/O."""

    def __init__(self) -> None:
        """Create an empty repository."""
        self._store: dict[uuid.UUID, Notebook] = {}

    def add(self, notebook: Notebook) -> None:
        """Record a notebook under its id."""
        self._store[notebook.id] = notebook

    def get(self, notebook_id: uuid.UUID) -> Notebook | None:
        """Return the notebook stored under notebook_id, or None."""
        return self._store.get(notebook_id)

    def count(self) -> int:
        """Return the number of stored notebooks."""
        return len(self._store)
