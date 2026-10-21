"""Per-test PostgreSQL schemas are migrated and dropped independently."""

import os
from collections.abc import Iterator
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

from lazyresearch.application.intake import IntakeService
from lazyresearch.infrastructure.persistence.database import database_engine
from lazyresearch.infrastructure.persistence.repositories import (
    SQLAlchemyIntakeStore,
    SQLAlchemyProcessingRepository,
)
from lazyresearch.infrastructure.sources.extract import SourceTextExtractor
from lazyresearch.infrastructure.sources.http import HTTPFetcher


@pytest.fixture
def db() -> Iterator[Engine]:
    value = os.environ.get("TEST_DATABASE_URL")
    if not value:
        pytest.fail("TEST_DATABASE_URL is required for real PostgreSQL integration tests")
    url = make_url(value)
    if (
        not url.database
        or not url.database.startswith("lazyresearch_")
        or not url.database.endswith("_test")
    ):
        pytest.fail("integration database must be isolated and named lazyresearch_*_test")
    admin = database_engine(value)
    schema = "lr_test_" + uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    test_url = url.set(drivername="postgresql+psycopg").update_query_dict(
        {"options": f"-csearch_path={schema}"}
    )
    engine = create_engine(test_url, hide_parameters=True, pool_pre_ping=True)
    try:
        config = Config("alembic.ini")
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def store(db: Engine) -> SQLAlchemyIntakeStore:
    return SQLAlchemyIntakeStore(db, extraction_version=SourceTextExtractor.version)


@pytest.fixture
def jobs(db: Engine) -> SQLAlchemyProcessingRepository:
    return SQLAlchemyProcessingRepository(db)


@pytest.fixture
def service(store: SQLAlchemyIntakeStore, jobs: SQLAlchemyProcessingRepository) -> IntakeService:
    return IntakeService(store, jobs, HTTPFetcher(), SourceTextExtractor())
