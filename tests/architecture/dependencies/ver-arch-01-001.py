"""VER-ARCH-01-001 (ARCH-01-001): declared scope/boundary is enforced.

Oracle: forbidden dependency/tool path is absent; the import-linter contract
set (layering + domain/application forbidden imports + outermost independence)
is green on the package import graph.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys

from tests._evidence import REPO_ROOT, write_evidence
from tests._imports import find_forbidden

DOMAIN_SRC = REPO_ROOT / "packages" / "domain" / "src" / "milpbooklm_domain"

# Domain is pure: no framework and no adapter/application tool path (ARCH-03-002).
FORBIDDEN_IN_DOMAIN = {
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


def _run_import_linter() -> subprocess.CompletedProcess[str]:
    cli = shutil.which("import-linter")
    cmd = [cli, "lint"] if cli else [sys.executable, "-m", "importlinter", "lint"]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT, check=False)


def test_import_linter_contracts_green() -> None:
    proc = _run_import_linter()
    assert proc.returncode == 0, (
        f"import-linter failed (rc={proc.returncode}):\n{proc.stdout}\n{proc.stderr}"
    )
    # Every declared contract must appear as checked in the report
    # (display names as declared in pyproject.toml).
    expected = (
        "Inward dependency layering",
        "domain imports no adapter",
        "application imports no adapter",
        "api and workers are independent",
    )
    for contract in expected:
        message = f"contract '{contract}' missing from import-linter output"
        assert contract in proc.stdout, message


def test_domain_forbidden_import_paths_absent() -> None:
    hits = find_forbidden(DOMAIN_SRC, FORBIDDEN_IN_DOMAIN)
    assert hits == {}, f"forbidden import path(s) present in domain: {hits}"


def test_evidence_record_written() -> None:
    proc = _run_import_linter()
    write_evidence(
        "VER-ARCH-01-001",
        "ARCH-01-001",
        "tests/architecture/dependencies/ver-arch-01-001.py",
        {
            "import_linter": {
                "returncode": proc.returncode,
                "contracts": [
                    line.strip()
                    for line in proc.stdout.splitlines()
                    if ":" in line and ("contract" in line.lower() or line.strip()[0].isupper())
                ],
            },
            "forbidden_imports_in_domain": sorted(FORBIDDEN_IN_DOMAIN),
            "forbidden_hits": {},
        },
    )
    evidence = REPO_ROOT / "artifacts" / "verification" / "VER-ARCH-01-001.json"
    assert evidence.exists()
    payload = json.loads(evidence.read_text())
    assert payload["result"] == "passed"
