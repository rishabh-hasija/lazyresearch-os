"""Deterministic citable chunking, transparent RRF, and bounded embedding work."""

from dataclasses import replace
from hashlib import sha256
from time import perf_counter
from uuid import NAMESPACE_URL, uuid5

from lazyresearch.application.intake_models import ContentExtraction
from lazyresearch.application.retrieval_models import (
    ChunkConfig,
    EmbeddingConfig,
    EmbeddingError,
    RetrievalRequest,
    RetrievalResult,
    ScoredChunk,
)
from lazyresearch.domain.chunks import ContentChunk
from lazyresearch.domain.identity import OwnerId
from lazyresearch.ports.errors import RepositoryError
from lazyresearch.ports.retrieval import EmbeddingProvider, EvidenceStore, VectorStore


def chunk_extraction(
    extraction: ContentExtraction, config: ChunkConfig
) -> tuple[ContentChunk, ...]:
    text = extraction.data.text
    ranges = (
        [(p.start, p.end, p.page) for p in extraction.data.pages]
        if extraction.data.pages
        else [(0, len(text), None)]
    )
    chunks: list[ContentChunk] = []
    for left, right, page in ranges:
        start = left
        while start < right:
            end = min(right, start + config.size)
            value = text[start:end]
            if value.strip():
                identity = f"{extraction.owner_id}:{extraction.id}:{config.identity}:{start}:{end}"
                chunks.append(
                    ContentChunk(
                        id=uuid5(NAMESPACE_URL, identity),
                        owner_id=extraction.owner_id,
                        content_id=extraction.content_id,
                        extraction_id=extraction.id,
                        ordinal=len(chunks),
                        start=start,
                        end=end,
                        page=page,
                        text=value,
                        chunker_version=config.identity,
                        text_hash=sha256(value.encode()).hexdigest(),
                    )
                )
            if end == right:
                break
            start = end - config.overlap
    return tuple(chunks)


class RetrieveEvidence:
    def __init__(
        self,
        store: EvidenceStore,
        chunks: ChunkConfig,
        vectors: VectorStore,
        provider: EmbeddingProvider,
        embeddings: EmbeddingConfig,
        *,
        vector_enabled: bool = False,
        rrf_k: int = 60,
        default_limit: int = 5,
        default_per_source: int = 2,
    ) -> None:
        if type(rrf_k) is not int or not 1 <= rrf_k <= 1000:
            raise ValueError("invalid RRF constant")
        self.store, self.chunks, self.vectors = store, chunks, vectors
        self.provider, self.embeddings = provider, embeddings
        self.vector_enabled, self.rrf_k = vector_enabled, rrf_k
        self.default_limit, self.default_per_source = default_limit, default_per_source

    def search(self, owner: OwnerId, query: str) -> RetrievalResult:
        return self.retrieve(
            RetrievalRequest(
                owner,
                query,
                vector=self.vector_enabled,
                limit=self.default_limit,
                per_source=self.default_per_source,
            )
        )

    def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        started = perf_counter()
        budget = min(200, max(30, request.limit * 4))
        lexical = (
            self.store.lexical(request, self.chunks.identity, budget) if request.lexical else ()
        )
        vector: tuple[ScoredChunk, ...] = ()
        status = "NOT_REQUESTED"
        if request.vector:
            status = "DISABLED"
            if self.vector_enabled:
                try:
                    if self.vectors.available():
                        batch = self.provider.embed((request.query,), self.embeddings, query=True)
                        if batch.config.namespace != self.embeddings.namespace:
                            raise EmbeddingError("MODEL_CHANGED")
                        vector = self.vectors.search(
                            request, self.chunks.identity, batch.vectors[0], self.embeddings, budget
                        )
                        status = "USED"
                    else:
                        status = "UNAVAILABLE"
                except (EmbeddingError, RepositoryError):
                    status = "FAILED"
        if request.vector and status != "USED" and not request.lexical:
            # Even an explicitly semantic query retains a visible lexical fallback on outage.
            lexical = self.store.lexical(request, self.chunks.identity, budget)
        lex = {hit.chunk_id: (i, hit.score) for i, hit in reversed(list(enumerate(lexical, 1)))}
        vec = {hit.chunk_id: (i, hit.score) for i, hit in reversed(list(enumerate(vector, 1)))}
        candidates = []
        # Resolve again with scope/visibility predicates, including for untrusted adapter hits.
        for candidate in self.store.resolve(
            request, self.chunks.identity, tuple(set(lex) | set(vec))
        ):
            chunk = candidate.chunk
            if chunk.owner_id != request.owner_id:
                continue
            lr, ls = lex.get(chunk.id, (None, None))
            vr, vs = vec.get(chunk.id, (None, None))
            score = sum(1 / (self.rrf_k + r) for r in (lr, vr) if r is not None)
            candidates.append(
                replace(
                    candidate,
                    lexical_rank=lr,
                    lexical_score=ls,
                    vector_rank=vr,
                    vector_score=vs,
                    fused_score=score,
                )
            )
        candidates.sort(key=lambda c: (-c.fused_score, str(c.chunk.id)))
        counts: dict[object, int] = {}
        selected = []
        for candidate in candidates:
            source = candidate.chunk.content_id
            if counts.get(source, 0) >= request.per_source:
                continue
            counts[source] = counts.get(source, 0) + 1
            selected.append(candidate)
            if len(selected) == request.limit:
                break
        return RetrievalResult(tuple(selected), status, perf_counter() - started)


class GenerateMissingEmbeddings:
    def __init__(
        self,
        store: VectorStore,
        provider: EmbeddingProvider,
        config: EmbeddingConfig,
        chunks: ChunkConfig,
    ) -> None:
        self.store, self.provider, self.config, self.chunks = store, provider, config, chunks

    def run(self, owner: OwnerId, *, limit: int = 20, retry: bool = False) -> dict[str, int]:
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("embedding work limit must be between 1 and 200")
        result = {"succeeded": 0, "failed": 0, "unavailable": 0}
        if not self.store.available():
            result["unavailable"] = 1
            return result
        attempted = set()
        for _ in range(limit):
            work = self.store.claim(owner, self.chunks.identity, self.config, retry=retry)
            if work is None or work.id in attempted:
                break
            attempted.add(work.id)
            try:
                batch = self.provider.embed((work.chunk.text,), self.config)
            except EmbeddingError as exc:
                self.store.fail(work, str(exc))
                result["failed"] += 1
                if retry:
                    break
                continue
            self.store.save(work, batch)
            result["succeeded"] += 1
        return result
