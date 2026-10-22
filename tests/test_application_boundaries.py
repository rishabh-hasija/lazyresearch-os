import ast
from pathlib import Path


def imports_in(source: str) -> list[str]:
    modules = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.append(node.module or "")
    return modules


def test_application_and_ports_do_not_import_infrastructure_or_providers() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "lazyresearch"
    for folder in ("application", "ports"):
        for path in (root / folder).rglob("*.py"):
            modules = imports_in(path.read_text(encoding="utf-8"))
            assert not any(
                module.startswith("lazyresearch.infrastructure") for module in modules
            ), path
            assert not {m.split(".")[0] for m in modules} & {
                "sqlalchemy",
                "psycopg",
                "alembic",
                "http",
                "requests",
                "httpx",
                "pypdf",
            }, path


def test_ui_uses_bootstrap_and_application_not_orm_or_partner_sdks() -> None:
    root = Path(__file__).resolve().parents[1] / "src/lazyresearch/ui"
    for path in root.rglob("*.py"):
        modules = imports_in(path.read_text(encoding="utf-8"))
        assert not any(m.startswith("lazyresearch.infrastructure") for m in modules), path
        assert not {m.split(".")[0] for m in modules} & {
            "sqlalchemy",
            "psycopg",
            "temporalio",
            "tabpfn",
            "requests",
            "httpx",
        }, path
