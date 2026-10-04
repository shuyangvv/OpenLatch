from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN = {
    "httpx",
    "openai",
    "langchain",
    "fastapi",
    "typesafe_sdk",
    "typesafe-sdk",
}

SRC = Path(__file__).resolve().parents[1] / "src" / "openlatch"


def _imported_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_import_graph_has_no_http_or_vendor_sdks() -> None:
    seen: set[str] = set()
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        seen.update(_imported_names(tree))
    assert seen.isdisjoint(FORBIDDEN)
