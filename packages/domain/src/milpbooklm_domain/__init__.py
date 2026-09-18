"""
Pure domain entities, policies and state machines.

This package imports only the standard library. Framework types (FastAPI,
SQLAlchemy, Pydantic) and all adapters are forbidden here by the import-linter
contract ``domain-forbidden`` (ARCH-03-002).
"""

from milpbooklm_domain.notebook import Notebook, NotebookStatus

__all__ = ["Notebook", "NotebookStatus"]
