"""Small independent embedding, vector-storage and evidence retrieval ports."""

from typing import Protocol
from uuid import UUID

from lazyresearch.application.retrieval_models import (
    ChunkConfig,
    EmbeddingBatch,
    EmbeddingConfig,
    EmbeddingWork,
    EvidenceCandidate,
    RetrievalRequest,
    ScoredChunk,
)
from lazyresearch.domain.identity import OwnerId


class EmbeddingProvider(Protocol):
    def embed(
        self, texts: tuple[str, ...], config: EmbeddingConfig, *, query: bool = False
    ) -> EmbeddingBatch: ...


class EvidenceStore(Protocol):
    def index(self, owner_id: OwnerId, config: ChunkConfig) -> int: ...
    def lexical(
        self, request: RetrievalRequest, version: str, limit: int
    ) -> tuple[ScoredChunk, ...]: ...
    def collection_context(
        self, request: RetrievalRequest, version: str
    ) -> tuple[EvidenceCandidate, ...]: ...
    def resolve(
        self, request: RetrievalRequest, version: str, ids: tuple[UUID, ...]
    ) -> tuple[EvidenceCandidate, ...]: ...


class VectorStore(Protocol):
    def available(self) -> bool: ...
    def claim(
        self, owner: OwnerId, chunk_version: str, config: EmbeddingConfig, *, retry: bool = False
    ) -> EmbeddingWork | None: ...
    def save(self, work: EmbeddingWork, batch: EmbeddingBatch) -> None: ...
    def fail(self, work: EmbeddingWork, code: str) -> None: ...
    def search(
        self,
        request: RetrievalRequest,
        version: str,
        vector: tuple[float, ...],
        config: EmbeddingConfig,
        limit: int,
    ) -> tuple[ScoredChunk, ...]: ...
    def delete_namespace(self, owner: OwnerId, namespace: str) -> int: ...
