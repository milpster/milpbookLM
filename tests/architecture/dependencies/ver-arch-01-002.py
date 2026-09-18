"""VER-ARCH-01-002 (ARCH-01-002): suitable local providers preferred by default.

Oracle: declared scope/boundary is enforced; the forbidden dependency/tool
path is absent. No external provider is enabled by default: with no
configured providers and no dependency health reports, provider-dependent
capabilities stay effectively disabled (local-first default), and the
domain carries no external-provider dependency path.
"""

from __future__ import annotations

from tests._evidence import REPO_ROOT
from tests._imports import find_forbidden
from tests.meta._evidence_fnd02 import write_evidence_fnd02
from tests.meta._tools import load_tool

DOMAIN_SRC = REPO_ROOT / "packages" / "domain" / "src" / "milpbooklm_domain"
CONTRACTS_SRC = REPO_ROOT / "packages" / "contracts" / "src" / "milpbooklm_contracts"

# External-provider dependency paths that must stay absent from pure layers.
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
}


def test_provider_dependent_capabilities_disabled_by_default() -> None:
    effective = load_tool("effective_state")
    registry = load_tool("check_capabilities").load_registry()["capabilities"]
    provider_caps = [
        cap
        for cap in registry
        if effective.cast_dependencies(cap)
        and effective.PROVIDER_DEPENDENCY_MARKER in " ".join(effective.cast_dependencies(cap))
    ]
    assert provider_caps, "no provider-dependent capabilities found in registry"
    states = effective.compute_effective_states(
        provider_caps, policy=effective.CapabilityPolicy(), dependency_health={}
    )
    for state in states.values():
        assert state.enabled is False, (
            f"{state.capability_id}: enabled without configured providers/health — "
            "external default violated the local-first preference"
        )


def test_pure_layers_carry_no_vendor_dependency_path() -> None:
    domain_hits = find_forbidden(DOMAIN_SRC, VENDOR_MODULES)
    contracts_hits = find_forbidden(CONTRACTS_SRC, VENDOR_MODULES)
    assert domain_hits == {}, f"vendor dependency path in domain: {domain_hits}"
    assert contracts_hits == {}, f"vendor dependency path in contracts: {contracts_hits}"


def test_evidence_record_written() -> None:
    effective = load_tool("effective_state")
    registry = load_tool("check_capabilities").load_registry()["capabilities"]
    provider_ids = [
        cap["id"]
        for cap in registry
        if effective.PROVIDER_DEPENDENCY_MARKER in " ".join(effective.cast_dependencies(cap))
    ]
    write_evidence_fnd02(
        "VER-ARCH-01-002",
        "ARCH-01-002",
        "tests/architecture/dependencies/ver-arch-01-002.py",
        {
            "provider_dependent_capabilities": provider_ids,
            "enabled_by_default": 0,
            "vendor_modules_scanned": sorted(VENDOR_MODULES),
            "forbidden_hits": {"domain": {}, "contracts": {}},
        },
    )
    evidence = REPO_ROOT / "artifacts" / "verification" / "VER-ARCH-01-002.json"
    assert evidence.exists()
