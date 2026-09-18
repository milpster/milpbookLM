"""VER-ARCH-01-004 (ARCH-01-004): content-bearing external calls stay disclosed.

Oracle: declared scope/boundary is enforced; the forbidden dependency/tool
path is absent. No model vendor, search engine or media provider may become
part of the domain/contracts layers (architecture central rule), so every
future external call can only reach a user through the provider adapter
boundary where the visible-disclosure obligation is enforced.
"""

from __future__ import annotations

from tests._evidence import REPO_ROOT
from tests._imports import find_forbidden
from tests.meta._evidence_fnd02 import write_evidence_fnd02

DOMAIN_SRC = REPO_ROOT / "packages" / "domain" / "src" / "milpbooklm_domain"
APPLICATION_SRC = REPO_ROOT / "packages" / "application" / "src" / "milpbooklm_application"
CONTRACTS_SRC = REPO_ROOT / "packages" / "contracts" / "src" / "milpbooklm_contracts"

VENDOR_MODULES = {
    "openai",
    "anthropic",
    "google",
    "googleapiclient",
    "azure",
    "botocore",
    "boto3",
    "cohere",
    "mistralai",
    "huggingface",
    "searxng",
}


def test_inner_layers_carry_no_external_provider_path() -> None:
    for label, source_dir in (
        ("domain", DOMAIN_SRC),
        ("application", APPLICATION_SRC),
        ("contracts", CONTRACTS_SRC),
    ):
        hits = find_forbidden(source_dir, VENDOR_MODULES)
        assert hits == {}, f"external provider dependency path in {label}: {hits}"


def test_evidence_record_written() -> None:
    hits = {
        label: find_forbidden(source_dir, VENDOR_MODULES)
        for label, source_dir in (
            ("domain", DOMAIN_SRC),
            ("application", APPLICATION_SRC),
            ("contracts", CONTRACTS_SRC),
        )
    }
    write_evidence_fnd02(
        "VER-ARCH-01-004",
        "ARCH-01-004",
        "tests/architecture/dependencies/ver-arch-01-004.py",
        {
            "scanned_layers": sorted(hits),
            "forbidden_hits": hits,
            "disclosure_boundary": (
                "provider adapter layer (apps/api + adapters) is the only external-call path"
            ),
        },
    )
    evidence = REPO_ROOT / "artifacts" / "verification" / "VER-ARCH-01-004.json"
    assert evidence.exists()
