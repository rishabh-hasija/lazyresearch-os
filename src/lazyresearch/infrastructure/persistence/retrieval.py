"""PostgreSQL lexical search and optional exact pgvector search with scope in SQL."""

import json
from dataclasses import asdict
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import Engine, bindparam, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from lazyresearch.application.intake_models import (
    ContentExtraction,
    ExtractionData,
    ExtractionStatus,
    PageSpan,
)
from lazyresearch.application.retrieval import chunk_extraction
from lazyresearch.application.retrieval_models import (
    ChunkConfig,
    EmbeddingBatch,
    EmbeddingConfig,
    EmbeddingWork,
    EvidenceCandidate,
    RetrievalRequest,
    ScoredChunk,
)
from lazyresearch.domain.chunks import ContentChunk
from lazyresearch.domain.identity import ContentId, OwnerId
from lazyresearch.infrastructure.persistence.models import ContentRow, ExtractionRow
from lazyresearch.infrastructure.persistence.repositories import DatabaseAdapter, lock
from lazyresearch.infrastructure.persistence.retrieval_models import (
    ChunkRow,
    CollectionRow,
    EmbeddingRow,
    MembershipRow,
    RetrievalStateRow,
)
from lazyresearch.ports.errors import RepositoryConflict

JOINS = """ JOIN content_item s ON s.id=c.content_id AND s.owner_id=c.owner_id
 JOIN retrieval_state r ON r.content_id=c.content_id AND r.owner_id=c.owner_id
  AND r.extraction_id=c.extraction_id AND r.visibility='ACTIVE'
 JOIN content_extraction x ON x.id=c.extraction_id AND x.owner_id=c.owner_id
  AND x.content_id=c.content_id """
SCOPE = """ c.owner_id=:owner AND c.chunker_version=:version AND x.status='SUCCEEDED'
 AND NOT EXISTS (SELECT 1 FROM content_extraction n WHERE n.owner_id=x.owner_id
  AND n.content_id=x.content_id AND (n.created_at>x.created_at OR
   (n.created_at=x.created_at AND n.id>x.id)))
 AND (NOT :filtered OR EXISTS (SELECT 1 FROM collection_membership m
  WHERE m.owner_id=c.owner_id AND m.content_id=c.content_id
   AND m.collection_id=ANY(CAST(:collections AS uuid[])))) """


def params(request: RetrievalRequest, version: str) -> dict[str, object]:
    return {
        "owner": request.owner_id,
        "version": version,
        "query": request.query,
        "filtered": bool(request.collection_ids),
        "collections": list(request.collection_ids),
        "source_cap": request.per_source,
    }


def chunk_value(row: ChunkRow) -> ContentChunk:
    return ContentChunk(**{k: getattr(row, k) for k in ContentChunk.__dataclass_fields__})


class PostgreSQLRetrievalStore(DatabaseAdapter):
    def index(self, owner_id: OwnerId, config: ChunkConfig) -> int:
        count = 0
        with self.transaction() as s:
            lock(s, f"chunks:{owner_id}")
            sources = s.scalars(
                select(ContentRow).where(ContentRow.owner_id == owner_id).order_by(ContentRow.id)
            )
            for source in sources:
                extraction = s.scalar(
                    select(ExtractionRow)
                    .where(
                        ExtractionRow.owner_id == owner_id, ExtractionRow.content_id == source.id
                    )
                    .order_by(ExtractionRow.created_at.desc(), ExtractionRow.id.desc())
                    .limit(1)
                )
                if extraction is None:
                    continue
                state = s.get(RetrievalStateRow, (owner_id, source.id))
                if state is None:
                    state = RetrievalStateRow(
                        owner_id=owner_id,
                        content_id=source.id,
                        extraction_id=extraction.id,
                        visibility="ACTIVE",
                    )
                    s.add(state)
                else:
                    state.extraction_id = extraction.id
                if extraction.status != "SUCCEEDED" or state.visibility != "ACTIVE":
                    continue
                value = ContentExtraction(
                    id=extraction.id,
                    owner_id=owner_id,
                    content_id=ContentId(source.id),
                    data=ExtractionData(
                        status=ExtractionStatus.SUCCEEDED,
                        version=extraction.version,
                        text=extraction.text,
                        normalized_hash=extraction.normalized_hash,
                        pages=tuple(PageSpan(**p) for p in extraction.pages),
                    ),
                )
                for chunk in chunk_extraction(value, config):
                    inserted = s.scalar(
                        insert(ChunkRow)
                        .values(**asdict(chunk))
                        .on_conflict_do_nothing(index_elements=["id"])
                        .returning(ChunkRow.id)
                    )
                    count += inserted is not None
        return count

    def lexical(
        self, request: RetrievalRequest, version: str, limit: int
    ) -> tuple[ScoredChunk, ...]:
        query = text(
            """WITH matches AS (SELECT c.id,c.content_id,
            ts_rank_cd(c.search, plainto_tsquery('simple',:query)) AS score
            FROM content_chunk c """
            + JOINS
            + " WHERE "
            + SCOPE
            + """
            AND c.search @@ plainto_tsquery('simple',:query)
            ), diversified AS (SELECT *,row_number() OVER (
              PARTITION BY content_id ORDER BY score DESC,id) AS source_rank FROM matches)
            SELECT id,score FROM diversified WHERE source_rank<=:source_cap
            ORDER BY score DESC,id LIMIT :limit"""
        )
        with self.transaction() as s:
            return tuple(
                ScoredChunk(row.id, float(row.score))
                for row in s.execute(query, {**params(request, version), "limit": limit})
            )

    def resolve(
        self, request: RetrievalRequest, version: str, ids: tuple[UUID, ...]
    ) -> tuple[EvidenceCandidate, ...]:
        if not ids:
            return ()
        query = text(
            "SELECT c.id,s.original_title,s.original_url,s.source_type FROM content_chunk c "
            + JOINS
            + " WHERE "
            + SCOPE
            + " AND c.id IN :ids"
        ).bindparams(bindparam("ids", expanding=True))
        with self.transaction() as s:
            result = []
            for row in s.execute(query, {**params(request, version), "ids": ids}):
                chunk = s.get(ChunkRow, row.id)
                assert chunk is not None
                result.append(
                    EvidenceCandidate(
                        chunk_value(chunk), row.original_title, row.original_url, row.source_type
                    )
                )
            return tuple(result)

    def set_visibility(self, owner: OwnerId, content: ContentId, visibility: str) -> None:
        if visibility not in {"ACTIVE", "ARCHIVED", "DELETION_PENDING", "DELETED"}:
            raise ValueError("unknown visibility")
        with self.transaction() as s:
            state = s.get(RetrievalStateRow, (owner, content), with_for_update=True)
            if state is None:
                raise RepositoryConflict("index source before changing retrieval visibility")
            state.visibility = visibility

    def create_collection(self, owner: OwnerId, name: str) -> UUID:
        if not name.strip() or len(name) > 120:
            raise ValueError("invalid collection name")
        with self.transaction() as s:
            row = CollectionRow(id=uuid4(), owner_id=owner, name=name)
            s.add(row)
            return row.id

    def add_to_collection(self, owner: OwnerId, collection: UUID, content: ContentId) -> None:
        with self.transaction() as s:
            s.execute(
                insert(MembershipRow)
                .values(owner_id=owner, collection_id=collection, content_id=content)
                .on_conflict_do_nothing()
            )


class PostgreSQLVectorStore(DatabaseAdapter):
    def __init__(self, engine: Engine, *, enabled: bool = True) -> None:
        super().__init__(engine)
        self.enabled = enabled

    def available(self) -> bool:
        if not self.enabled:
            return False
        with self.transaction() as s:
            return bool(
                s.scalar(
                    text(
                        "SELECT to_regclass('embedding_vector') IS NOT NULL "
                        "AND EXISTS (SELECT 1 FROM pg_extension WHERE extname='vector' "
                        "AND extnamespace='public'::regnamespace)"
                    )
                )
            )

    def claim(
        self, owner: OwnerId, chunk_version: str, config: EmbeddingConfig, *, retry: bool = False
    ) -> EmbeddingWork | None:
        if not self.available():
            return None
        with self.transaction() as s:
            # Serializes only short reservation transactions, never model inference.
            lock(s, f"embedding:{owner}:{config.namespace}")
            query = text(
                "SELECT c.id FROM content_chunk c " + JOINS + " WHERE " + SCOPE + " ORDER BY c.id"
            )
            dummy = RetrievalRequest(owner, "index")
            now = s.scalar(select(func.clock_timestamp()))
            assert isinstance(now, datetime)
            for chunk_id in s.scalars(query, params(dummy, chunk_version)):
                row = s.scalar(
                    select(EmbeddingRow)
                    .where(
                        EmbeddingRow.owner_id == owner,
                        EmbeddingRow.chunk_id == chunk_id,
                        EmbeddingRow.namespace == config.namespace,
                    )
                    .with_for_update()
                )
                if row is not None and (
                    row.status == "SUCCEEDED"
                    or row.status == "RUNNING"
                    and row.expires_at is not None
                    and row.expires_at > now
                    or row.status == "FAILED"
                    and not retry
                ):
                    continue
                if row is None:
                    row = EmbeddingRow(
                        id=uuid4(),
                        owner_id=owner,
                        chunk_id=chunk_id,
                        namespace=config.namespace,
                        provider=config.provider,
                        model=config.model,
                        revision=config.revision,
                        dimension=config.dimension,
                        normalization=config.normalization,
                        attempts=0,
                    )
                    s.add(row)
                row.status, row.token = "RUNNING", uuid4()
                row.expires_at = now + timedelta(seconds=config.timeout + 30)
                row.attempts += 1
                row.error = None
                chunk = s.get(ChunkRow, chunk_id)
                assert chunk is not None
                return EmbeddingWork(row.id, row.token, chunk_value(chunk))
            return None

    @staticmethod
    def active(s: Session, work: EmbeddingWork) -> EmbeddingRow:
        row = s.scalar(
            select(EmbeddingRow)
            .where(
                EmbeddingRow.id == work.id,
                EmbeddingRow.owner_id == work.chunk.owner_id,
                EmbeddingRow.chunk_id == work.chunk.id,
                EmbeddingRow.status == "RUNNING",
                EmbeddingRow.token == work.token,
                EmbeddingRow.expires_at > func.clock_timestamp(),
            )
            .with_for_update()
        )
        if row is None:
            raise RepositoryConflict("embedding lease expired or replaced")
        state = s.get(RetrievalStateRow, (work.chunk.owner_id, work.chunk.content_id))
        if (
            state is None
            or state.visibility != "ACTIVE"
            or state.extraction_id != work.chunk.extraction_id
        ):
            raise RepositoryConflict("embedding source no longer current or visible")
        return row

    def save(self, work: EmbeddingWork, batch: EmbeddingBatch) -> None:
        if len(batch.vectors) != 1:
            raise RepositoryConflict("one embedding per reserved chunk")
        with self.transaction() as s:
            row = self.active(s, work)
            if row.namespace != batch.config.namespace or row.dimension != batch.config.dimension:
                raise RepositoryConflict("embedding space differs from reservation")
            s.execute(
                text(
                    "INSERT INTO embedding_vector(embedding_id,dimension,embedding) "
                    "VALUES (:id,:dimension,CAST(:value AS public.vector))"
                ),
                {"id": row.id, "dimension": row.dimension, "value": json.dumps(batch.vectors[0])},
            )
            row.status, row.token, row.expires_at = "SUCCEEDED", None, None
            row.latency_seconds, row.runtime = batch.latency_seconds, batch.runtime

    def fail(self, work: EmbeddingWork, code: str) -> None:
        safe = (
            code
            if code
            in {
                "INPUT_BOUNDS",
                "TIMEOUT",
                "UNAVAILABLE",
                "INVALID_RESPONSE",
                "MODEL_CHANGED",
                "DIMENSION_OR_VALUES",
                "ZERO_VECTOR",
            }
            else "PROVIDER_ERROR"
        )
        with self.transaction() as s:
            row = self.active(s, work)
            row.status, row.error, row.token, row.expires_at = "FAILED", safe, None, None

    def search(
        self,
        request: RetrievalRequest,
        version: str,
        vector: tuple[float, ...],
        config: EmbeddingConfig,
        limit: int,
    ) -> tuple[ScoredChunk, ...]:
        if not self.available():
            return ()
        EmbeddingBatch((vector,), config, 0)  # Enforce dimensional/finite/normalization contract.
        query = text(
            """WITH matches AS (SELECT c.id,c.content_id, 1-(v.embedding OPERATOR(public.<=>)
            CAST(:vector AS public.vector)) AS score FROM embedding_vector v
            JOIN content_embedding e ON e.id=v.embedding_id AND e.dimension=v.dimension
            JOIN content_chunk c ON c.id=e.chunk_id AND c.owner_id=e.owner_id """
            + JOINS
            + " WHERE "
            + SCOPE
            + """ AND e.namespace=:namespace AND e.status='SUCCEEDED'
            AND e.dimension=:dimension), diversified AS (SELECT *,row_number() OVER (
              PARTITION BY content_id ORDER BY score DESC,id) AS source_rank FROM matches)
            SELECT id,score FROM diversified WHERE source_rank<=:source_cap
            ORDER BY score DESC,id LIMIT :limit"""
        )
        with self.transaction() as s:
            return tuple(
                ScoredChunk(row.id, float(row.score))
                for row in s.execute(
                    query,
                    {
                        **params(request, version),
                        "vector": json.dumps(vector),
                        "namespace": config.namespace,
                        "dimension": config.dimension,
                        "limit": limit,
                    },
                )
            )

    def delete_namespace(self, owner: OwnerId, namespace: str) -> int:
        with self.transaction() as s:
            result = s.execute(
                text(
                    "DELETE FROM content_embedding WHERE owner_id=:owner AND namespace=:namespace "
                    "RETURNING id"
                ),
                {"owner": owner, "namespace": namespace},
            )
            return len(result.all())
