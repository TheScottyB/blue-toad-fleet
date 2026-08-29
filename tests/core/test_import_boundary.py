# tests/core/test_import_boundary.py
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "src" / "blue_toad"
FORBIDDEN_PREFIXES = (
    "scripts",
    "src.server",
    "src.gate",
    "src.memory",
    "src.bidmath",
)


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_processing_core_does_not_import_runners_ui_memory_or_bidmath():
    py_files = sorted(CORE.rglob("*.py"))
    assert py_files, f"expected a src/blue_toad package at {CORE}"
    violations: list[str] = []
    for path in py_files:
        for name in _imported_modules(path):
            if name == "scripts" or name.startswith("scripts."):
                violations.append(f"{path.relative_to(ROOT)} imports {name}")
            for prefix in FORBIDDEN_PREFIXES:
                if name == prefix or name.startswith(prefix + "."):
                    violations.append(f"{path.relative_to(ROOT)} imports {name}")
    assert violations == []
