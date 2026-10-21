"""Tests may read ignored .env; production configuration reads environment only."""

import os
from pathlib import Path

pytest_plugins = ["tests.db_fixtures", "tests.http_fixtures"]


def pytest_configure() -> None:
    path = Path(__file__).resolve().parents[1] / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                name, value = line.split("=", 1)
                if name in {"TEST_DATABASE_URL", "MIGRATION_TEST_DATABASE_URL"}:
                    os.environ.setdefault(name, value)
