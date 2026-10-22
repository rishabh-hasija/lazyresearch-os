"""Composition for intake and source analysis; no CLI, UI or startup migration."""

from dataclasses import replace

from sqlalchemy import Engine

from lazyresearch.application.analysis import ProcessPendingContent
from lazyresearch.application.intake import IntakeService
from lazyresearch.application.mission_models import MissionScope
from lazyresearch.application.missions import ResearchOperations
from lazyresearch.application.relevance import CatchUp
from lazyresearch.application.relevance_models import RankingUnavailable
from lazyresearch.application.retrieval import GenerateMissingEmbeddings, RetrieveEvidence
from lazyresearch.infrastructure.ai.embeddings import OllamaEmbeddings
from lazyresearch.infrastructure.ai.ollama import OllamaProcessor, configured_ollama
from lazyresearch.infrastructure.ai.synthesis import OllamaResearchSynthesizer
from lazyresearch.infrastructure.config import Settings
from lazyresearch.infrastructure.persistence.analysis import SQLAlchemyAnalysisStore
from lazyresearch.infrastructure.persistence.database import database_engine
from lazyresearch.infrastructure.persistence.missions import PostgreSQLMissionStore
from lazyresearch.infrastructure.persistence.ranking import PostgreSQLRankingStore
from lazyresearch.infrastructure.persistence.repositories import (
    SQLAlchemyIntakeStore,
    SQLAlchemyProcessingRepository,
)
from lazyresearch.infrastructure.persistence.retrieval import (
    PostgreSQLRetrievalStore,
    PostgreSQLVectorStore,
)
from lazyresearch.infrastructure.ranking import TabPFNRankingModel
from lazyresearch.infrastructure.search import SerpApiSearch
from lazyresearch.infrastructure.sources.extract import SourceTextExtractor
from lazyresearch.infrastructure.sources.http import HTTPFetcher


def build_catch_up(
    settings: Settings,
    *,
    engine: Engine | None = None,
    tabpfn_path: str | None = None,
) -> CatchUp:
    database = engine if engine is not None else database_engine(settings.database_url)
    store = PostgreSQLRankingStore(database)
    try:
        return CatchUp(store, TabPFNRankingModel(tabpfn_path) if tabpfn_path else None)
    except RankingUnavailable:
        return CatchUp(store, unavailable=True)


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


def build_retrieval(settings: Settings, *, engine: Engine | None = None) -> RetrieveEvidence:
    if settings.embeddings.provider != "ollama":
        raise ValueError("unsupported EMBEDDING_PROVIDER")
    database = engine if engine is not None else database_engine(settings.database_url)
    config = settings.embeddings
    if settings.vector_search_enabled:
        revision, _ = OllamaProcessor(settings.embedding_endpoint).metadata(config.model)
        config = replace(config, revision=revision)
    return RetrieveEvidence(
        PostgreSQLRetrievalStore(database),
        settings.chunks,
        PostgreSQLVectorStore(database, enabled=settings.vector_search_enabled),
        OllamaEmbeddings(settings.embedding_endpoint),
        config,
        vector_enabled=settings.vector_search_enabled,
        rrf_k=settings.rrf_k,
        default_limit=settings.retrieval_limit,
        default_per_source=settings.retrieval_per_source,
    )


def build_embeddings(
    settings: Settings, *, engine: Engine | None = None
) -> GenerateMissingEmbeddings:
    retrieval = build_retrieval(settings, engine=engine)
    return GenerateMissingEmbeddings(
        retrieval.vectors, retrieval.provider, retrieval.embeddings, retrieval.chunks
    )


def default_mission_scope(settings: Settings, *, public: bool = False) -> MissionScope:
    return MissionScope(
        public=public,
        vector=settings.vector_search_enabled,
        max_queries=settings.search_max_queries,
        max_sources=settings.search_max_results,
    )


def build_research(settings: Settings, *, engine: Engine | None = None) -> ResearchOperations:
    if settings.search_provider != "serpapi" or settings.ai.provider != "ollama":
        raise ValueError("unsupported research provider")
    database = engine if engine is not None else database_engine(settings.database_url)
    return ResearchOperations(
        PostgreSQLMissionStore(database),
        build_retrieval(settings, engine=database),
        build_intake(settings, engine=database),
        SerpApiSearch(
            settings.serpapi_api_key, settings.search_timeout_seconds, settings.search_max_results
        ),
        OllamaResearchSynthesizer(
            settings.ai_endpoint, settings.ai.model, settings.ai.timeout_seconds
        ),
    )
