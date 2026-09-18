"""Notebook entity and its status state machine (pure, stdlib-only)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum


class NotebookStatus(StrEnum):
    """Lifecycle states of a notebook."""

    ACTIVE = "active"
    ARCHIVED = "archived"


@dataclass(frozen=True, slots=True)
class Notebook:
    """A research notebook aggregate root (immutable value object)."""

    id: uuid.UUID
    title: str
    status: NotebookStatus = NotebookStatus.ACTIVE

    def archive(self) -> Notebook:
        """Return a new archived notebook; the original is unchanged."""
        if self.status is NotebookStatus.ARCHIVED:
            return self
        return Notebook(id=self.id, title=self.title, status=NotebookStatus.ARCHIVED)
