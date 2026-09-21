"""VER-ARCH-03-001 (ARCH-03-001): dependency direction matches the system map.

Oracle: the composition root wires use cases to adapters, and adapters depend
only on application ports + domain (no framework at this layer in the
skeleton; the direction is what is asserted).
"""

from __future__ import annotations

import sys

from milpbooklm_api.composition import build_create_notebook

from tests._evidence import REPO_ROOT, write_evidence
from tests._imports import imported_top_level_modules

ADAPTERS_SRC = REPO_ROOT / "packages" / "adapters" / "src" / "milpbooklm_adapters"
# The package's own name appears because __init__.py re-exports via absolute
# self-imports; that is the package's identity, not a dependency.
# sqlalchemy/alembic/psycopg: the FND-03 persistence line, named verbatim in
# REFERENCE-DEPENDENCIES.md ("SQLAlchemy 2, Alembic, psycopg 3").
# argon2: the FND-04 identity line, named verbatim in REFERENCE-DEPENDENCIES.md
# (Passwords row: "argon2-cffi").
# nacl: the FND-07 credential-encryption line (PyNaCl binding), named in
# REFERENCE-DEPENDENCIES.md ("libsodium XChaCha20-Poly1305 through a
# maintained binding").
# httpx: the MOD-01 dedicated provider transport (REFERENCE-DEPENDENCIES.md HTTP
# row: "httpx/httpcore only behind the dedicated fetch/provider transports").
# pydantic: the REFERENCE-DEPENDENCIES.md API line (Pydantic v2) for the adapter's
# private response boundary models.
# anyio: the httpx/httpcore async transport backend (MOD-01 streaming adapter).
# pypdf/pdfplumber/pdfminer: the ING-01b PDF chain named verbatim in the parser matrix.
# openpyxl/docx/pptx: the ING-02a office rows named verbatim in the parser matrix
# ("openpyxl read-only/data-only", "python-docx", "python-pptx").
ALLOWED_ADAPTER_IMPORTS = {
    "milpbooklm_adapters",
    "milpbooklm_domain",
    "milpbooklm_application",
    "milpbooklm_contracts",
    "sqlalchemy",
    "alembic",
    "psycopg",
    "argon2",
    "nacl",
    "httpx",
    "pydantic",
    "anyio",
    "pypdf",
    "pdfplumber",
    "pdfminer",
    "openpyxl",
    "docx",
    "pptx",
} | set(sys.stdlib_module_names)


def test_composition_wires_use_case_to_adapter() -> None:
    create_notebook, repository = build_create_notebook()
    notebook = create_notebook("Atlas")
    repository.add(notebook)
    fetched = repository.get(notebook.id)
    assert fetched is not None
    assert fetched.id == notebook.id
    assert fetched.title == "Atlas"
    assert repository.count() == 1


def test_adapter_dependency_direction_inward_only() -> None:
    imports = imported_top_level_modules(ADAPTERS_SRC)
    violations = imports - ALLOWED_ADAPTER_IMPORTS
    message = f"adapters import modules outside the allowed set: {sorted(violations)}"
    assert violations == set(), message


def test_evidence_record_written() -> None:
    write_evidence(
        "VER-ARCH-03-001",
        "ARCH-03-001",
        "tests/architecture/composition/ver-arch-03-001.py",
        {
            "composition": (
                "build_create_notebook() -> CreateNotebook + InMemoryNotebookRepository; "
                "create/store/fetch exercised"
            ),
            "adapter_imports": sorted(imported_top_level_modules(ADAPTERS_SRC)),
            "allowed_adapter_imports_policy": (
                "stdlib + internal packages + REFERENCE-DEPENDENCIES.md third parties "
                "(sqlalchemy, alembic, psycopg, argon2, nacl)"
            ),
        },
    )
    evidence = REPO_ROOT / "artifacts" / "verification" / "VER-ARCH-03-001.json"
    assert evidence.exists()
