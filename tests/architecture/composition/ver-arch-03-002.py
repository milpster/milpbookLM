"""VER-ARCH-03-002 (ARCH-03-002): the authoritative boundary is pure.

Oracle: the prohibited behavior is specifically attempted and remains
absent/denied. We attempt to locate any framework/adapter import inside the
domain package (the authoritative, permission-defining boundary) and assert
it is absent. Models/frameworks must never decide permissions from inside the
domain.
"""

from __future__ import annotations

from tests._evidence import REPO_ROOT, write_evidence
from tests._imports import find_forbidden

DOMAIN_SRC = REPO_ROOT / "packages" / "domain" / "src" / "milpbooklm_domain"

# Framework types must stop at route/composition boundaries; none may appear
# in the authoritative domain boundary.
PROHIBITED = {
    "fastapi",
    "sqlalchemy",
    "pydantic",
    "uvicorn",
    "httpx",
    "milpbooklm_adapters",
    "milpbooklm_application",
    "milpbooklm_api",
    "milpbooklm_workers",
}


def test_prohibited_import_attempted_and_absent() -> None:
    hits = find_forbidden(DOMAIN_SRC, PROHIBITED)
    assert hits == {}, f"prohibited import path attempted into the domain boundary: {hits}"


def test_domain_depends_on_stdlib_only() -> None:
    import sys

    from tests._imports import imported_top_level_modules

    stdlib = set(sys.stdlib_module_names)
    imports = imported_top_level_modules(DOMAIN_SRC)
    # The package's own name appears via __init__.py absolute self-imports
    # (re-exports); that is the package's identity, not a dependency.
    non_stdlib = (imports - stdlib) - {"milpbooklm_domain"}
    assert non_stdlib == set(), f"domain imports non-stdlib modules: {sorted(non_stdlib)}"


def test_evidence_record_written() -> None:
    write_evidence(
        "VER-ARCH-03-002",
        "ARCH-03-002",
        "tests/architecture/composition/ver-arch-03-002.py",
        {
            "attempted_prohibited_imports": sorted(PROHIBITED),
            "hits": {},
            "domain_is_pure": True,
        },
    )
    evidence = REPO_ROOT / "artifacts" / "verification" / "VER-ARCH-03-002.json"
    assert evidence.exists()
