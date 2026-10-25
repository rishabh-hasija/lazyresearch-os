"""Explicit configuration; no credentials or providers are hard-coded."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlsplit

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
    search_provider: str = "serpapi"
    serpapi_api_key: str = field(default="", repr=False)
    search_max_queries: int = 3
    search_max_results: int = 10
    search_timeout_seconds: float = 20
    temporal_address: str = field(default="", repr=False)
    temporal_namespace: str = "default"
    temporal_task_queue: str = "lazyresearch-missions-v1"

    temporal_api_key: str = field(default="", repr=False)
    temporal_tls: bool | None = None

    def __post_init__(self) -> None:
        self.validate_temporal()
        if not 1 <= self.retrieval_limit <= 50 or not 1 <= self.retrieval_per_source <= 20:
            raise ValueError("invalid retrieval defaults")
        if not 1 <= self.rrf_k <= 1000:
            raise ValueError("invalid RRF constant")
        if (
            not 0 <= self.search_max_queries <= 3
            or not 1 <= self.search_max_results <= 10
            or not 1 <= self.search_timeout_seconds <= 60
        ):
            raise ValueError("invalid public search budget")

    def validate_temporal(self, *, required: bool = False) -> None:
        if self.temporal_tls is not None and not isinstance(self.temporal_tls, bool):
            raise ValueError("TEMPORAL_TLS must be true or false")
        if not self.temporal_address:
            if required or self.temporal_api_key or self.temporal_tls:
                raise ValueError("TEMPORAL_ADDRESS is required when Temporal is enabled")
            return
        try:
            target = urlsplit("//" + self.temporal_address)
            valid = (
                bool(target.hostname)
                and target.port is not None
                and 1 <= target.port <= 65535
                and target.username is None
                and target.password is None
                and not target.path
                and not target.query
                and not target.fragment
                and not any(c.isspace() for c in self.temporal_address)
            )
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("TEMPORAL_ADDRESS must be host:port without URL or credentials")
        if not self.temporal_namespace.strip() or not self.temporal_task_queue.strip():
            raise ValueError("TEMPORAL_NAMESPACE and TEMPORAL_TASK_QUEUE must not be empty")
        if self.temporal_api_key and any(c.isspace() for c in self.temporal_api_key):
            raise ValueError("TEMPORAL_API_KEY must not contain whitespace")
        if self.temporal_cloud:
            if not self.temporal_api_key:
                raise ValueError("TEMPORAL_API_KEY is required for Temporal Cloud")
            if self.temporal_namespace == "default":
                raise ValueError("TEMPORAL_NAMESPACE must be configured for Temporal Cloud")
        if (self.temporal_api_key or self.temporal_cloud) and self.temporal_tls is False:
            raise ValueError("TEMPORAL_TLS must be enabled for API-key authentication or Cloud")

    @property
    def temporal_cloud(self) -> bool:
        host = (urlsplit("//" + self.temporal_address).hostname or "").lower().rstrip(".")
        return host.endswith((".tmprl.cloud", ".temporal.io"))

    @property
    def temporal_tls_enabled(self) -> bool:
        if self.temporal_tls is not None:
            return self.temporal_tls
        return bool(self.temporal_api_key) or self.temporal_cloud

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
        tls = values.get("TEMPORAL_TLS", "").strip().lower()
        if tls not in {"", "true", "false"}:
            raise ValueError("TEMPORAL_TLS must be true or false")
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
            search_provider=values.get("SEARCH_PROVIDER", "serpapi"),
            serpapi_api_key=values.get("SERPAPI_API_KEY", ""),
            search_max_queries=int(values.get("SEARCH_MAX_QUERIES", "3")),
            search_max_results=int(values.get("SEARCH_MAX_RESULTS", "10")),
            search_timeout_seconds=float(values.get("SEARCH_TIMEOUT_SECONDS", "20")),
            temporal_address=values.get("TEMPORAL_ADDRESS", ""),
            temporal_api_key=values.get("TEMPORAL_API_KEY", ""),
            temporal_tls=None if not tls else tls == "true",
            temporal_namespace=values.get("TEMPORAL_NAMESPACE", "default"),
            temporal_task_queue=values.get("TEMPORAL_TASK_QUEUE", "lazyresearch-missions-v1"),
        )
