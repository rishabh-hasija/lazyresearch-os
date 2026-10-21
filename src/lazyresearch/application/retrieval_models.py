"""Bounded retrieval/embedding contracts, separate from generative analysis."""

import json
import math
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from uuid import UUID

from lazyresearch.domain.chunks import ContentChunk
from lazyresearch.domain.identity import OwnerId


@dataclass(frozen=True, slots=True)
class ChunkConfig:
    size: int = 1000
    overlap: int = 150
    version: str = "chars-pages-v1"

    def __post_init__(self) -> None:
        if (
            type(self.size) is not int
            or type(self.overlap) is not int
            or not 1 <= self.size <= 4000
            or not 0 <= self.overlap < self.size
            or not self.version.strip()
        ):
            raise ValueError("invalid chunk configuration")

    @property
    def identity(self) -> str:
        return f"{self.version}:{self.size}:{self.overlap}"


@dataclass(frozen=True, slots=True)
class EmbeddingConfig:
    provider: str = "ollama"
    model: str = "qwen3-embedding:latest"
    revision: str | None = None
    dimension: int = 4096
    normalization: str = "l2-v1"
    version: str = "retrieval-v1"
    query_instruction: str = "Instruct: Retrieve relevant saved source passages.\nQuery: "
    max_chars: int = 4000
    batch_size: int = 4
    timeout: float = 120

    def __post_init__(self) -> None:
        if (
            not self.provider.strip()
            or not self.model.strip()
            or not self.version.strip()
            or type(self.dimension) is not int
            or not 1 <= self.dimension <= 16000
            or self.normalization != "l2-v1"
            or not 1 <= self.max_chars <= 8000
            or not 1 <= self.batch_size <= 16
            or not math.isfinite(self.timeout)
            or not 0 < self.timeout <= 600
        ):
            raise ValueError("invalid embedding configuration")

    @property
    def namespace(self) -> str:
        # Time/batch budgets do not change the vector space. Query formatting does.
        values = {
            k: v for k, v in asdict(self).items() if k not in {"max_chars", "batch_size", "timeout"}
        }
        return sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class EmbeddingBatch:
    vectors: tuple[tuple[float, ...], ...] = field(repr=False)
    config: EmbeddingConfig
    latency_seconds: float
    runtime: str | None = None
    input_norms: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "vectors", tuple(tuple(v) for v in self.vectors))
        if not self.vectors or not math.isfinite(self.latency_seconds) or self.latency_seconds < 0:
            raise ValueError("invalid embedding result")
        for vector in self.vectors:
            if (
                len(vector) != self.config.dimension
                or any(type(x) not in (int, float) or not math.isfinite(x) for x in vector)
                or not math.isclose(sum(x * x for x in vector), 1, abs_tol=1e-4)
            ):
                raise ValueError("invalid embedding dimension, values or normalization")


class EmbeddingError(Exception):
    """Only sanitized operational categories cross the provider port."""


@dataclass(frozen=True, slots=True)
class RetrievalRequest:
    owner_id: OwnerId
    query: str = field(repr=False)
    collection_ids: tuple[UUID, ...] = ()
    lexical: bool = True
    vector: bool = False
    limit: int = 5
    per_source: int = 2

    def __post_init__(self) -> None:
        if not isinstance(self.owner_id, UUID):
            raise ValueError("owner scope required")
        object.__setattr__(self, "collection_ids", tuple(self.collection_ids))
        if (
            not self.query.strip()
            or len(self.query) > 500
            or len(self.query.encode()) > 2000
            or not self.lexical
            and not self.vector
            or type(self.limit) is not int
            or not 1 <= self.limit <= 50
            or type(self.per_source) is not int
            or not 1 <= self.per_source <= 20
            or len(self.collection_ids) > 20
            or any(not isinstance(v, UUID) for v in self.collection_ids)
        ):
            raise ValueError("invalid retrieval request")


@dataclass(frozen=True, slots=True)
class ScoredChunk:
    chunk_id: UUID
    score: float


@dataclass(frozen=True, slots=True)
class EvidenceCandidate:
    chunk: ContentChunk
    title: str | None
    source_url: str | None
    source_type: str
    lexical_rank: int | None = None
    lexical_score: float | None = None
    vector_rank: int | None = None
    vector_score: float | None = None
    fused_score: float = 0


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    candidates: tuple[EvidenceCandidate, ...]
    vector_status: str
    latency_seconds: float


@dataclass(frozen=True, slots=True)
class EmbeddingWork:
    id: UUID
    token: UUID
    chunk: ContentChunk
