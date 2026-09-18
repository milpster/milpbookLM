"""Loader for the standalone tools/spec scripts used by VER meta-tests (FND-02)."""

from __future__ import annotations

import importlib.util
import sys
import types

from tests._evidence import REPO_ROOT

TOOLS_SPEC = REPO_ROOT / "tools" / "spec"


def load_tool(name: str) -> types.ModuleType:
    """Import a tools/spec script by file name under a unique module name."""
    path = TOOLS_SPEC / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"tools_spec_{name}", path)
    assert spec is not None, f"tool spec is None for {path}"
    assert spec.loader is not None, f"tool spec loader is None for {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
