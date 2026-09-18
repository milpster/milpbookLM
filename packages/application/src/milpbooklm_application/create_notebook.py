"""CreateNotebook use case: a port-agnostic operation over the domain."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from milpbooklm_domain.notebook import Notebook


@dataclass(frozen=True, slots=True)
class CreateNotebook:
    """Use case that materializes a new active notebook."""

    def __call__(self, title: str) -> Notebook:
        """Return a new active notebook for the given title."""
        if not title.strip():
            raise ValueError("notebook title must be non-empty")
        return Notebook(id=uuid.uuid4(), title=title.strip())
