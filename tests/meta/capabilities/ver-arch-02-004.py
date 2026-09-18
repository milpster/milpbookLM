"""VER-ARCH-02-004 (ARCH-02-004): ordinary vs agentic chat distinction preserved.

Oracle: classification, phase, dependencies and applicability match the
parity matrix. Ordinary chat stays grounded and tool-free (Phase 1 core);
agentic chat is the separate tool-capable path (Phase 3, research
dependencies), never merged into one capability.
"""

from __future__ import annotations

from tests._evidence import REPO_ROOT
from tests.meta._evidence_fnd02 import write_evidence_fnd02
from tests.meta._tools import load_tool

# Frozen phases: ordinary chat is Phase 1 core, agentic chat is Phase 3.
GROUNDED_CHAT_PHASE = 1
AGENTIC_CHAT_PHASE = 3


def _caps() -> dict[str, dict]:
    return {
        cap["id"]: cap for cap in load_tool("check_capabilities").load_registry()["capabilities"]
    }


def test_ordinary_chat_is_grounded_and_tool_free() -> None:
    cap = _caps()["grounded_chat"]
    assert cap["classification"] == "stable/core"
    assert cap["phase"] == GROUNDED_CHAT_PHASE
    text = cap["reference_text"]
    assert "stays grounded in selected notebook material" in text
    assert "does not silently use the open web/tools" in text
    assert "searxng" not in cap["dependencies"], "ordinary chat must remain tool-free"


def test_agentic_chat_is_the_separate_tool_capable_path() -> None:
    cap = _caps()["agentic_chat"]
    assert cap["classification"] == "stable/core"
    assert cap["phase"] == AGENTIC_CHAT_PHASE, (
        "agentic chat is a Phase 3 capability, distinct from ordinary chat"
    )
    assert "searxng" in cap["dependencies"], "agentic chat must declare searxng as a dependency"
    assert "playwright" in cap["dependencies"], (
        "agentic chat must declare playwright as a dependency"
    )


def test_evidence_record_written() -> None:
    caps = _caps()
    write_evidence_fnd02(
        "VER-ARCH-02-004",
        "ARCH-02-004",
        "tests/meta/capabilities/ver-arch-02-004.py",
        {
            "grounded_chat": {
                "phase": caps["grounded_chat"]["phase"],
                "tool_free": True,
            },
            "agentic_chat": {
                "phase": caps["agentic_chat"]["phase"],
                "dependencies": caps["agentic_chat"]["dependencies"],
            },
        },
    )
    evidence = REPO_ROOT / "artifacts" / "verification" / "VER-ARCH-02-004.json"
    assert evidence.exists()
