"""Small static guard for the core's explicitly allowed imports, not a sandbox."""

import ast
from pathlib import Path

import pytest

ALLOWED_STANDARD_MODULES = {"dataclasses", "datetime", "enum", "hashlib", "typing", "uuid"}


def violations(source: str) -> list[str]:
    errors = []
    for node in ast.walk(ast.parse(source)):
        modules = []
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                errors.append("relative import: use an explicit domain path")
            modules = [node.module or ""]
        for module in modules:
            if module.split(".")[0] in ALLOWED_STANDARD_MODULES:
                continue
            if module == "lazyresearch.domain" or module.startswith("lazyresearch.domain."):
                continue
            errors.append(f"forbidden import: {module}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"__import__", "open", "eval", "exec"}:
                errors.append(f"forbidden dynamic/I-O call: {node.func.id}")
    return errors


def test_domain_has_only_pure_standard_library_and_domain_imports() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "lazyresearch" / "domain"
    modules = sorted(root.rglob("*.py"))
    assert modules
    errors = {p.name: violations(p.read_text(encoding="utf-8")) for p in modules}
    assert all(not problems for problems in errors.values()), errors


@pytest.mark.parametrize(
    "source",
    [
        "import sqlalchemy",
        "from temporalio import workflow",
        "import streamlit",
        "from lazyresearch.ports.content import ContentRepository",
        "from lazyresearch.infrastructure import database",
        "import pathlib",
        "import socket",
        "__import__('ollama')",
        "open('source.txt')",
    ],
)
def test_guard_detects_representative_boundary_violations(source: str) -> None:
    assert violations(source)
