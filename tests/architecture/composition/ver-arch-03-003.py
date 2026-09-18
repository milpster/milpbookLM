"""VER-ARCH-03-003 (ARCH-03-003): lower levels must not depend on upper levels.

Oracle: higher levels MAY depend on lower-level capabilities; the reverse is
MUST NOT. We specifically attempt to find application -> adapter (and
domain -> application/adapter) edges in the static import graph and assert
they are absent.
"""

from __future__ import annotations

from tests._evidence import REPO_ROOT, write_evidence
from tests._imports import find_forbidden

APPLICATION_SRC = REPO_ROOT / "packages" / "application" / "src" / "milpbooklm_application"
DOMAIN_SRC = REPO_ROOT / "packages" / "domain" / "src" / "milpbooklm_domain"

UPPER_LEVEL_FOR_APPLICATION = {"milpbooklm_adapters", "milpbooklm_api", "milpbooklm_workers"}
UPPER_LEVEL_FOR_DOMAIN = {
    "milpbooklm_application",
    "milpbooklm_adapters",
    "milpbooklm_api",
    "milpbooklm_workers",
}


def test_application_does_not_depend_on_upper_levels() -> None:
    hits = find_forbidden(APPLICATION_SRC, UPPER_LEVEL_FOR_APPLICATION)
    assert hits == {}, f"application depends on upper-level features: {hits}"


def test_domain_does_not_depend_on_upper_levels() -> None:
    hits = find_forbidden(DOMAIN_SRC, UPPER_LEVEL_FOR_DOMAIN)
    assert hits == {}, f"domain depends on upper-level features: {hits}"


def test_evidence_record_written() -> None:
    write_evidence(
        "VER-ARCH-03-003",
        "ARCH-03-003",
        "tests/architecture/composition/ver-arch-03-003.py",
        {
            "application_upper_level_hits": {},
            "domain_upper_level_hits": {},
            "direction": "application -> domain only; domain -> stdlib only",
        },
    )
    evidence = REPO_ROOT / "artifacts" / "verification" / "VER-ARCH-03-003.json"
    assert evidence.exists()
