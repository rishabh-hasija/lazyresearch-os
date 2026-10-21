from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from lazyresearch.application.intake_models import IntakeInput
from lazyresearch.application.retrieval import GenerateMissingEmbeddings, RetrieveEvidence
from lazyresearch.application.retrieval_models import (
    ChunkConfig,
    EmbeddingBatch,
    EmbeddingConfig,
    RetrievalRequest,
)
from lazyresearch.domain.content import SourceType
from lazyresearch.domain.identity import OwnerId
from lazyresearch.infrastructure.persistence.retrieval import (
    PostgreSQLRetrievalStore,
    PostgreSQLVectorStore,
)
from lazyresearch.infrastructure.persistence.retrieval_models import ChunkRow, EmbeddingRow
from lazyresearch.ports.errors import RepositoryConflict
from tests.test_retrieval import FakeEmbedding

pytestmark = pytest.mark.integration


def source(service, owner, key, value):
    return (
        service.ingest(
            owner,
            key,
            (IntakeInput(source_type=SourceType.TEXT, payload=value.encode(), title=key),),
        )
        .entries[0]
        .content_id
    )


def fixture(db, service):
    owner = OwnerId(uuid4())
    content = source(service, owner, "solar", "Solar battery renewable electricity. " * 8)
    other = source(service, owner, "cats", "Cats rest near a warm fireplace.")
    foreign = OwnerId(uuid4())
    source(service, foreign, "private", "Solar battery private secret.")
    store = PostgreSQLRetrievalStore(db)
    chunks = ChunkConfig(size=80, overlap=15)
    store.index(owner, chunks)
    store.index(foreign, chunks)
    vectors = PostgreSQLVectorStore(db)
    config = EmbeddingConfig(dimension=3, model="fake", revision="fixture")
    usecase = RetrieveEvidence(store, chunks, vectors, FakeEmbedding(), config, vector_enabled=True)
    return owner, content, other, store, chunks, vectors, config, usecase


def test_lexical_exact_tokens_limits_scoping_and_no_embeddings(db, service):
    owner, content, _, store, chunks, _, _, usecase = fixture(db, service)
    result = usecase.retrieve(RetrievalRequest(owner, "solar battery", limit=3, per_source=1))
    assert len(result.candidates) == 1 and result.candidates[0].chunk.content_id == content
    assert result.candidates[0].chunk.evidence.quote in "Solar battery renewable electricity. " * 8
    assert store.index(owner, chunks) == 0
    assert not usecase.retrieve(RetrievalRequest(owner, "private secret")).candidates


@pytest.mark.parametrize("state", ["ARCHIVED", "DELETION_PENDING", "DELETED"])
def test_visibility_excluded_from_lexical_and_vector(db, service, state):
    owner, content, _, store, chunks, vectors, config, usecase = fixture(db, service)
    assert vectors.available()
    GenerateMissingEmbeddings(vectors, FakeEmbedding(), config, chunks).run(owner)
    store.set_visibility(owner, content, state)
    result = usecase.retrieve(RetrievalRequest(owner, "solar", vector=True, limit=20))
    assert all(c.chunk.content_id != content for c in result.candidates)
    assert not usecase.retrieve(RetrievalRequest(owner, "solar")).candidates


def test_collection_filter_many_to_many_owner_safe(db, service):
    owner, content, other, store, _, _, _, usecase = fixture(db, service)
    first = store.create_collection(owner, "Home")
    second = store.create_collection(owner, "Energy")
    store.add_to_collection(owner, first, content)
    store.add_to_collection(owner, second, content)
    store.add_to_collection(owner, second, other)
    assert (
        len(usecase.retrieve(RetrievalRequest(owner, "solar", collection_ids=(first,))).candidates)
        > 0
    )
    assert not usecase.retrieve(RetrievalRequest(owner, "cats", collection_ids=(first,))).candidates
    with pytest.raises(RepositoryConflict):
        store.add_to_collection(OwnerId(uuid4()), first, content)
    assert not usecase.retrieve(
        RetrievalRequest(OwnerId(uuid4()), "solar", collection_ids=(first,))
    ).candidates


def test_vector_namespace_metadata_nearest_and_owner(db, service):
    owner, content, _, store, chunks, vectors, config, usecase = fixture(db, service)
    generator = GenerateMissingEmbeddings(vectors, FakeEmbedding(), config, chunks)
    assert generator.run(owner)["succeeded"] > 0
    assert generator.run(owner)["succeeded"] == 0
    hits = vectors.search(
        RetrievalRequest(owner, "solar"), chunks.identity, (1.0, 0.0, 0.0), config, 10
    )
    assert hits and all(h.score > 0.999 for h in hits)
    assert not vectors.search(
        RetrievalRequest(OwnerId(uuid4()), "solar"), chunks.identity, (1.0, 0.0, 0.0), config, 10
    )
    second = replace(config, version="second")
    assert not vectors.search(
        RetrievalRequest(owner, "solar"), chunks.identity, (1.0, 0.0, 0.0), second, 10
    )
    assert (
        GenerateMissingEmbeddings(vectors, FakeEmbedding(), second, chunks).run(owner)["succeeded"]
        > 0
    )
    with Session(db) as s:
        values = list(s.scalars(select(EmbeddingRow)))
        assert {r.namespace for r in values} == {config.namespace, second.namespace}
        assert all(
            r.dimension == 3 and r.normalization == "l2-v1" and r.runtime == "fake-runtime"
            for r in values
        )
    assert vectors.delete_namespace(owner, second.namespace) > 0
    assert usecase.retrieve(RetrievalRequest(owner, "solar", vector=True)).candidates


def test_embedding_failure_retry_and_stale_fence(db, service):
    owner, _, _, _, chunks, vectors, config, _ = fixture(db, service)
    assert (
        GenerateMissingEmbeddings(vectors, FakeEmbedding(error=True), config, chunks).run(
            owner, limit=1
        )["failed"]
        == 1
    )
    assert (
        GenerateMissingEmbeddings(vectors, FakeEmbedding(), config, chunks).run(
            owner, limit=1, retry=True
        )["succeeded"]
        == 1
    )
    work = vectors.claim(owner, chunks.identity, config)
    with db.begin() as c:
        c.execute(
            update(EmbeddingRow)
            .where(EmbeddingRow.id == work.id)
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    replacement = vectors.claim(owner, chunks.identity, config)
    assert replacement.id == work.id and replacement.token != work.token
    with pytest.raises(RepositoryConflict):
        vectors.save(work, EmbeddingBatch(((1.0, 0.0, 0.0),), config, 0))
    with pytest.raises(ValueError):
        EmbeddingBatch(((1.0, 0.0),), config, 0)


def test_version_selection_and_immutable_old_chunks(db, service, store, jobs):
    owner = OwnerId(uuid4())
    content = source(service, owner, "old", "obsolete keyword")
    retrieval = PostgreSQLRetrievalStore(db)
    config = ChunkConfig()
    retrieval.index(owner, config)
    initial = retrieval.lexical(RetrievalRequest(owner, "obsolete"), config.identity, 10)
    from lazyresearch.infrastructure.persistence.repositories import SQLAlchemyIntakeStore
    from lazyresearch.infrastructure.sources.extract import success

    newer = SQLAlchemyIntakeStore(db, extraction_version="new-extractor")
    lease = newer.create_batch(
        owner, "new", (IntakeInput(source_type=SourceType.TEXT, payload=b"obsolete keyword"),)
    )
    # Queue a new extractor through the same capture path, then save another derived version.
    claim = newer.claim_entry(owner, newer.batch(owner, lease).entries[0].id)
    from lazyresearch.application.intake_models import FetchedSource

    newer.save_original(
        claim,
        FetchedSource(
            payload=b"obsolete keyword",
            final_url="",
            fetched_at=datetime.now(UTC),
            content_type="text/plain",
            http_status=0,
        ),
    )
    extraction_lease = jobs.claim(owner, "EXTRACT", content_id=content, version="new-extractor")
    newer.save_extraction(extraction_lease, success("current replacement", "new-extractor"))
    assert not retrieval.lexical(RetrievalRequest(owner, "obsolete"), config.identity, 10)
    retrieval.index(owner, config)
    assert retrieval.lexical(RetrievalRequest(owner, "replacement"), config.identity, 10)
    with Session(db) as s:
        assert s.get(ChunkRow, initial[0].chunk_id).text == "obsolete keyword"
    retrieval.index(owner, replace(config, version="new-chunker"))
    with pytest.raises(DBAPIError), db.begin() as c:
        c.execute(text("UPDATE content_chunk SET text=text"))


def test_optional_migration_disabled_then_upgrade(db, service):
    owner = OwnerId(uuid4())
    source(service, owner, "before", "solar fallback")
    config = Config("alembic.ini")
    with db.begin() as c:
        config.attributes["connection"] = c
        command.downgrade(config, "0002")
        config.attributes["disable_vector"] = True
        command.upgrade(config, "head")
    store = PostgreSQLRetrievalStore(db)
    chunks = ChunkConfig()
    store.index(owner, chunks)
    assert not PostgreSQLVectorStore(db).available()
    assert store.lexical(RetrievalRequest(owner, "solar"), chunks.identity, 5)
    with db.begin() as c:
        config.attributes["connection"] = c
        command.downgrade(config, "0002")
        config.attributes["disable_vector"] = False
        command.upgrade(config, "head")
    assert PostgreSQLVectorStore(db).available()


def test_exact_vector_nearest_and_collection_scope(db, service):
    owner, content, other, store, chunks, vectors, config, _ = fixture(db, service)
    while (work := vectors.claim(owner, chunks.identity, config)) is not None:
        value = (1.0, 0.0, 0.0) if work.chunk.content_id == content else (0.0, 1.0, 0.0)
        vectors.save(work, EmbeddingBatch((value,), config, 0.01, "fake-runtime"))
    hits = vectors.search(
        RetrievalRequest(owner, "electricity"), chunks.identity, (1.0, 0.0, 0.0), config, 1
    )
    resolved = store.resolve(
        RetrievalRequest(owner, "electricity"), chunks.identity, tuple(h.chunk_id for h in hits)
    )
    assert resolved[0].chunk.content_id == content and hits[0].score > 0.999
    collection = store.create_collection(owner, "Pets")
    store.add_to_collection(owner, collection, other)
    scoped = RetrievalRequest(owner, "electricity", collection_ids=(collection,))
    restricted = vectors.search(scoped, chunks.identity, (1.0, 0.0, 0.0), config, 5)
    assert restricted and all(
        c.chunk.content_id == other
        for c in store.resolve(scoped, chunks.identity, tuple(h.chunk_id for h in restricted))
    )


def test_sql_diversification_prevents_long_source_candidate_starvation(db, service):
    owner = OwnerId(uuid4())
    source(service, owner, "long", "solar " * 1000)
    short = source(service, owner, "short", "solar")
    store, chunks = PostgreSQLRetrievalStore(db), ChunkConfig(size=40, overlap=0)
    store.index(owner, chunks)
    request = RetrievalRequest(owner, "solar", limit=5, per_source=1)
    hits = store.lexical(request, chunks.identity, 5)
    evidence = store.resolve(request, chunks.identity, tuple(h.chunk_id for h in hits))
    assert len(evidence) == 2 and short in {e.chunk.content_id for e in evidence}


def test_real_pdf_persisted_chunks_and_database_quote_page_guard(db, service):
    from tests.integration.test_pdf import pdf_bytes

    owner = OwnerId(uuid4())
    service.ingest(
        owner,
        "pdf-chunks",
        (IntakeInput(source_type=SourceType.PDF, payload=pdf_bytes(), filename="synthetic.pdf"),),
    )
    store, chunks = PostgreSQLRetrievalStore(db), ChunkConfig()
    store.index(owner, chunks)
    hits = store.lexical(RetrievalRequest(owner, "Synthetic page"), chunks.identity, 5)
    evidence = store.resolve(
        RetrievalRequest(owner, "Synthetic page"), chunks.identity, tuple(h.chunk_id for h in hits)
    )
    assert {c.chunk.page for c in evidence} == {1, 2}
    original = evidence[0].chunk
    from dataclasses import asdict

    invalid = {**asdict(original), "id": uuid4(), "chunker_version": "bad", "page": 999}
    with pytest.raises(DBAPIError), db.begin() as c:
        c.execute(ChunkRow.__table__.insert().values(**invalid))
