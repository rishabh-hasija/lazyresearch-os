"""Composition for intake and source analysis; no CLI, UI or startup migration."""

from sqlalchemy import Engine

from lazyresearch.application.analysis import ProcessPendingContent
from lazyresearch.application.intake import IntakeService
from lazyresearch.infrastructure.ai.ollama import configured_ollama
from lazyresearch.infrastructure.config import Settings
from lazyresearch.infrastructure.persistence.analysis import SQLAlchemyAnalysisStore
from lazyresearch.infrastructure.persistence.database import database_engine
from lazyresearch.infrastructure.persistence.repositories import (
    SQLAlchemyIntakeStore,
    SQLAlchemyProcessingRepository,
)
from lazyresearch.infrastructure.sources.extract import SourceTextExtractor
from lazyresearch.infrastructure.sources.http import HTTPFetcher


def build_intake(settings: Settings, *, engine: Engine | None = None) -> IntakeService:
    database = engine if engine is not None else database_engine(settings.database_url)
    extractor = SourceTextExtractor(settings.limits)
    return IntakeService(
        SQLAlchemyIntakeStore(
            database, extraction_version=extractor.version, limits=settings.limits
        ),
        SQLAlchemyProcessingRepository(database, lease_seconds=settings.limits.lease_seconds),
        HTTPFetcher(settings.limits),
        extractor,
        settings.limits,
    )


def build_processing(settings: Settings, *, engine: Engine | None = None) -> ProcessPendingContent:
    if settings.ai.provider != "ollama":
        raise ValueError("unsupported AI_PROVIDER")
    database = engine if engine is not None else database_engine(settings.database_url)
    processor, config = configured_ollama(settings.ai, settings.ai_endpoint)
    return ProcessPendingContent(SQLAlchemyAnalysisStore(database), processor, config)
