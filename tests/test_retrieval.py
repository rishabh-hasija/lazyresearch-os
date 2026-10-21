from dataclasses import replace
from uuid import uuid4

import pytest

from lazyresearch.application.intake_models import PageSpan
from lazyresearch.application.retrieval import RetrieveEvidence, chunk_extraction
from lazyresearch.application.retrieval_models import (
    ChunkConfig,
    EmbeddingBatch,
    EmbeddingConfig,
    EmbeddingError,
    EvidenceCandidate,
    RetrievalRequest,
    ScoredChunk,
)
from lazyresearch.domain.identity import OwnerId
from lazyresearch.infrastructure.ai.embeddings import OllamaEmbeddings
from lazyresearch.infrastructure.config import Settings
from tests.analysis_helpers import work_for


def test_chunks_stable_overlap_unicode_offsets_and_version():
    work, _ = work_for("😀abcdefghi")
    config = ChunkConfig(size=5, overlap=2)
    chunks = chunk_extraction(work.extraction, config)
    assert chunks == chunk_extraction(work.extraction, config)
    assert [(c.start, c.end) for c in chunks] == [(0, 5), (3, 8), (6, 10)]
    assert chunks[0].text[-2:] == chunks[1].text[:2]
    assert all(c.evidence.quote == work.extraction.data.text[c.start : c.end] for c in chunks)
    new = chunk_extraction(work.extraction, replace(config, version="v2"))
    assert new[0].id != chunks[0].id and new[0].text == chunks[0].text


def test_pdf_chunks_do_not_cross_pages_or_cite_separator():
    work, _ = work_for(
        "first\nsecond", pages=(PageSpan(page=1, start=0, end=5), PageSpan(page=2, start=6, end=12))
    )
    chunks = chunk_extraction(work.extraction, ChunkConfig(size=100, overlap=0))
    assert [(c.start, c.end, c.page) for c in chunks] == [(0, 5, 1), (6, 12, 2)]


@pytest.mark.parametrize(
    "changes",
    [{"size": 0}, {"overlap": -1}, {"size": 5, "overlap": 5}, {"size": True}, {"version": ""}],
)
def test_chunk_bounds(changes):
    with pytest.raises(ValueError):
        ChunkConfig(**changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"query": " "},
        {"query": "a" * 501},
        {"limit": 0},
        {"per_source": 0},
        {"lexical": False, "vector": False},
        {"collection_ids": ("foreign",)},
    ],
)
def test_request_bounds(changes):
    with pytest.raises(ValueError):
        RetrievalRequest(**{"owner_id": OwnerId(uuid4()), "query": "solar", **changes})


class FakeEmbedding:
    def __init__(self, error=False):
        self.error = error
        self.calls = []

    def embed(self, texts, config, *, query=False):
        self.calls.append((texts, query))
        if self.error:
            raise EmbeddingError("UNAVAILABLE")
        return EmbeddingBatch(tuple((1.0, 0.0, 0.0) for _ in texts), config, 0.01, "fake-runtime")


class FakeSources:
    def __init__(self, chunks):
        self.chunks = chunks
        self.hits = ()

    def lexical(self, request, version, limit):
        return self.hits

    def resolve(self, request, version, ids):
        # Deliberately untrusted adapter output tests the application owner defense.
        return tuple(
            EvidenceCandidate(c, "Title", None, "TEXT") for c in self.chunks if c.id in ids
        )


class FakeVectors:
    def __init__(self, hits=(), available=True):
        self.hits, self.enabled = hits, available

    def available(self):
        return self.enabled

    def search(self, *args):
        return self.hits


def test_hybrid_rrf_union_dedup_diversification_and_owner_defense():
    a, _ = work_for("one two three four five six")
    b, _ = work_for("second source")
    foreign, _ = work_for("foreign secret")
    b = replace(b, extraction=replace(b.extraction, owner_id=a.lease.owner_id))
    chunks = chunk_extraction(a.extraction, ChunkConfig(size=10, overlap=0))
    other = chunk_extraction(b.extraction, ChunkConfig())[0]
    secret = chunk_extraction(foreign.extraction, ChunkConfig())[0]
    sources = FakeSources((*chunks, other, secret))
    sources.hits = (ScoredChunk(chunks[0].id, 10), ScoredChunk(chunks[1].id, 9))
    vectors = FakeVectors(
        (
            ScoredChunk(chunks[0].id, 0.99),
            ScoredChunk(other.id, 0.9),
            ScoredChunk(other.id, 0.8),
            ScoredChunk(secret.id, 0.7),
        )
    )
    usecase = RetrieveEvidence(
        sources,
        ChunkConfig(),
        vectors,
        FakeEmbedding(),
        EmbeddingConfig(dimension=3),
        vector_enabled=True,
    )
    request = RetrievalRequest(a.lease.owner_id, "query", vector=True, limit=5, per_source=1)
    result = usecase.retrieve(request)
    assert [c.chunk.id for c in result.candidates] == [chunks[0].id, other.id]
    assert result.candidates[0].fused_score == 2 / 61
    assert result.candidates[0].lexical_rank == result.candidates[0].vector_rank == 1
    assert result.candidates[1].lexical_rank is None
    assert result.vector_status == "USED"
    full = usecase.retrieve(replace(request, per_source=2))
    assert {c.chunk.id for c in full.candidates} == {chunks[0].id, chunks[1].id, other.id}
    assert full.candidates == usecase.retrieve(replace(request, per_source=2)).candidates


@pytest.mark.parametrize(
    "enabled,available,error,status",
    [
        (False, True, False, "DISABLED"),
        (True, False, False, "UNAVAILABLE"),
        (True, True, True, "FAILED"),
    ],
)
def test_vector_failure_always_leaves_lexical_fallback(enabled, available, error, status):
    work, _ = work_for()
    chunk = chunk_extraction(work.extraction, ChunkConfig())[0]
    sources = FakeSources((chunk,))
    sources.hits = (ScoredChunk(chunk.id, 1),)
    usecase = RetrieveEvidence(
        sources,
        ChunkConfig(),
        FakeVectors(available=available),
        FakeEmbedding(error),
        EmbeddingConfig(dimension=3),
        vector_enabled=enabled,
    )
    result = usecase.retrieve(
        RetrievalRequest(work.lease.owner_id, "submit", lexical=False, vector=True)
    )
    assert len(result.candidates) == 1 and result.vector_status == status


def embedding_wire(vector=None, failure=None):
    calls = []

    def wire(path, body, timeout):
        calls.append((path, body))
        if path == "/api/version":
            return {"version": "test-runtime"}
        if path == "/api/tags":
            return {"models": [{"name": "qwen3-embedding:latest", "digest": "test-digest"}]}
        if failure:
            raise failure
        return {"model": "qwen3-embedding:latest", "embeddings": [vector or [3.0, 4.0, 0.0]]}

    return wire, calls


def test_embedding_adapter_metadata_query_instruction_and_normalization():
    wire, calls = embedding_wire()
    config = EmbeddingConfig(dimension=3, revision="test-digest")
    result = OllamaEmbeddings("http://localhost", wire=wire).embed(("battery",), config, query=True)
    assert result.vectors[0] == (0.6, 0.8, 0) and result.input_norms == (5.0,)
    assert result.config == config and result.runtime == "test-runtime"
    request = calls[-1][1]
    assert request["truncate"] is False and request["input"] == [
        config.query_instruction + "battery"
    ]


@pytest.mark.parametrize(
    "vector", [[1.0, 0.0], [float("nan"), 0.0, 1.0], [0.0, 0.0, 0.0], [True, 0.0, 1.0]]
)
def test_embedding_adapter_invalid_dimension_values(vector):
    wire, _ = embedding_wire(vector)
    with pytest.raises(EmbeddingError):
        OllamaEmbeddings("http://localhost", wire=wire).embed(
            ("source",), EmbeddingConfig(dimension=3)
        )


def test_embedding_space_versions_and_configuration():
    config = EmbeddingConfig()
    assert config.namespace != replace(config, version="new").namespace
    assert config.namespace != replace(config, revision="new").namespace
    assert config.namespace != replace(config, dimension=3).namespace
    settings = Settings.from_env(
        {
            "DATABASE_URL": "postgresql://example/db",
            "VECTOR_SEARCH_ENABLED": "true",
            "CHUNK_SIZE_CHARS": "700",
            "CHUNK_OVERLAP_CHARS": "80",
            "EMBEDDING_BATCH_SIZE": "2",
            "RETRIEVAL_LIMIT": "9",
        }
    )
    assert settings.vector_search_enabled and settings.chunks.size == 700
    assert settings.embeddings.batch_size == 2 and settings.retrieval_limit == 9


def test_embedding_adapter_returns_actual_known_revision_when_unspecified():
    wire, _ = embedding_wire()
    result = OllamaEmbeddings("http://localhost", wire=wire).embed(
        ("source",), EmbeddingConfig(dimension=3)
    )
    assert result.config.revision == "test-digest"


@pytest.mark.parametrize("texts", [(), ("",), ("a" * 4001,), ("a",) * 5])
def test_embedding_adapter_bounds_before_network(texts):
    wire, calls = embedding_wire()
    with pytest.raises(EmbeddingError, match="INPUT_BOUNDS"):
        OllamaEmbeddings("http://localhost", wire=wire).embed(texts, EmbeddingConfig(dimension=3))
    assert not calls
