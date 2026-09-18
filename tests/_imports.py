"""Static import-graph scans used by the architecture VER tests (FND-01)."""

from __future__ import annotations

import ast
from pathlib import Path


def imported_top_level_modules(source_dir: Path) -> set[str]:
    """Collect the top-level module names imported by every .py under source_dir."""
    modules: set[str] = set()
    for path in sorted(source_dir.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    modules.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0:
                modules.add(node.module.split(".")[0])
    return modules


def find_forbidden(package_src: Path, forbidden: set[str]) -> dict[str, list[str]]:
    """Return {module: [importing files]} for every forbidden import found."""
    hits: dict[str, list[str]] = {}
    for path in sorted(package_src.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module.split(".")[0]] if node.module and node.level == 0 else []
            for name in names:
                if name in forbidden:
                    hits.setdefault(name, []).append(str(path.relative_to(package_src)))
    return hits
