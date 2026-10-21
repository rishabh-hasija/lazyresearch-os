"""Explicit configuration; no credentials or providers are hard-coded."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

from lazyresearch.application.analysis_models import AnalysisConfig
from lazyresearch.application.intake_models import IntakeLimits
from lazyresearch.application.retrieval_models import ChunkConfig, EmbeddingConfig


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str = field(repr=False)
    limits: IntakeLimits = IntakeLimits()
    ai: AnalysisConfig = AnalysisConfig()
    ai_endpoint: str = "http://127.0.0.1:11434"
    chunks: ChunkConfig = ChunkConfig()
    embeddings: EmbeddingConfig = EmbeddingConfig()
    embedding_endpoint: str = "http://127.0.0.1:11434"
    vector_search_enabled: bool = False
    retrieval_limit: int = 5
    retrieval_per_source: int = 2
    rrf_k: int = 60

    def __post_init__(self) -> None:
        if not 1 <= self.retrieval_limit <= 50 or not 1 <= self.retrieval_per_source <= 20:
            raise ValueError("invalid retrieval defaults")
        if not 1 <= self.rrf_k <= 1000:
            raise ValueError("invalid RRF constant")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        values = os.environ if env is None else env
        url = values.get("DATABASE_URL", "")
        if not url:
            raise ValueError("DATABASE_URL is required")
        defaults = IntakeLimits()
        kwargs: dict[str, int | float] = {}
        for name in defaults.__dataclass_fields__:
            key = name.upper()
            if key in values:
                kwargs[name] = float(values[key]) if "timeout" in name else int(values[key])
        # Each field is numeric; individual fields are validated by IntakeLimits.
        limits = IntakeLimits(**kwargs)  # type: ignore[arg-type]
        ai = AnalysisConfig(
            provider=values.get("AI_PROVIDER", "ollama"),
            model=values.get("AI_MODEL", "gemma4:e4b"),
            timeout_seconds=float(values.get("AI_TIMEOUT_SECONDS", "120")),
            max_input_chars=int(values.get("AI_MAX_INPUT_CHARS", "4000")),
            max_chunks=int(values.get("AI_MAX_CHUNKS", "64")),
            max_output_tokens=int(values.get("AI_MAX_OUTPUT_TOKENS", "2400")),
        )
        enabled = values.get("VECTOR_SEARCH_ENABLED", "false").lower()
        if enabled not in {"true", "false"}:
            raise ValueError("VECTOR_SEARCH_ENABLED must be true or false")
        return cls(
            url,
            limits,
            ai,
            values.get("AI_ENDPOINT", "http://127.0.0.1:11434"),
            ChunkConfig(
                size=int(values.get("CHUNK_SIZE_CHARS", "1000")),
                overlap=int(values.get("CHUNK_OVERLAP_CHARS", "150")),
            ),
            EmbeddingConfig(
                provider=values.get("EMBEDDING_PROVIDER", "ollama"),
                model=values.get("EMBEDDING_MODEL", "qwen3-embedding:latest"),
                dimension=int(values.get("EMBEDDING_DIMENSION", "4096")),
                timeout=float(values.get("EMBEDDING_TIMEOUT_SECONDS", "120")),
                batch_size=int(values.get("EMBEDDING_BATCH_SIZE", "4")),
            ),
            values.get("EMBEDDING_ENDPOINT", "http://127.0.0.1:11434"),
            enabled == "true",
            int(values.get("RETRIEVAL_LIMIT", "5")),
            int(values.get("RETRIEVAL_PER_SOURCE_LIMIT", "2")),
            int(values.get("RRF_K", "60")),
        )
