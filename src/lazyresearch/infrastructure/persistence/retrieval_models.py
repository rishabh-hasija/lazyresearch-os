"""Retrieval ORM metadata; optional native vectors use a migration-managed side table."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    Float,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from lazyresearch.infrastructure.persistence.models import Base


class RetrievalStateRow(Base):
    __tablename__ = "retrieval_state"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "content_id"], ["content_item.owner_id", "content_item.id"]
        ),
        ForeignKeyConstraint(
            ["owner_id", "content_id", "extraction_id"],
            [
                "content_extraction.owner_id",
                "content_extraction.content_id",
                "content_extraction.id",
            ],
        ),
        CheckConstraint(
            "visibility IN ('ACTIVE','ARCHIVED','DELETION_PENDING','DELETED')",
            name="retrieval_visibility",
        ),
    )
    owner_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    content_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    extraction_id: Mapped[UUID] = mapped_column(Uuid)
    visibility: Mapped[str] = mapped_column(String(24), default="ACTIVE")


class ChunkRow(Base):
    __tablename__ = "content_chunk"
    __table_args__ = (
        UniqueConstraint("owner_id", "id"),
        UniqueConstraint("owner_id", "extraction_id", "chunker_version", "ordinal"),
        ForeignKeyConstraint(
            ["owner_id", "content_id", "extraction_id"],
            [
                "content_extraction.owner_id",
                "content_extraction.content_id",
                "content_extraction.id",
            ],
        ),
        CheckConstraint('start >= 0 AND "end" > start AND ordinal >= 0', name="chunk_span"),
        CheckConstraint(
            "encode(sha256(convert_to(text,'UTF8')),'hex')=text_hash", name="chunk_hash"
        ),
        Index("ix_chunk_lexical", "search", postgresql_using="gin"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid)
    content_id: Mapped[UUID] = mapped_column(Uuid)
    extraction_id: Mapped[UUID] = mapped_column(Uuid)
    ordinal: Mapped[int] = mapped_column(Integer)
    start: Mapped[int] = mapped_column(Integer)
    end: Mapped[int] = mapped_column(Integer)
    page: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    chunker_version: Mapped[str] = mapped_column(Text)
    text_hash: Mapped[str] = mapped_column(String(64))
    search: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('simple'::regconfig, text)", persisted=True)
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CollectionRow(Base):
    __tablename__ = "collection"
    __table_args__ = (UniqueConstraint("owner_id", "id"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid)
    name: Mapped[str] = mapped_column(Text)


class MembershipRow(Base):
    __tablename__ = "collection_membership"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "collection_id"], ["collection.owner_id", "collection.id"]
        ),
        ForeignKeyConstraint(
            ["owner_id", "content_id"], ["content_item.owner_id", "content_item.id"]
        ),
    )
    owner_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    collection_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    content_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)


class EmbeddingRow(Base):
    __tablename__ = "content_embedding"
    __table_args__ = (
        UniqueConstraint("owner_id", "chunk_id", "namespace"),
        UniqueConstraint("id", "dimension"),
        ForeignKeyConstraint(
            ["owner_id", "chunk_id"], ["content_chunk.owner_id", "content_chunk.id"]
        ),
        CheckConstraint("dimension BETWEEN 1 AND 16000", name="embedding_dimension"),
        CheckConstraint("status IN ('RUNNING','SUCCEEDED','FAILED')", name="embedding_status"),
        CheckConstraint(
            "(status='RUNNING') = (token IS NOT NULL AND expires_at IS NOT NULL)",
            name="embedding_lease",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid)
    chunk_id: Mapped[UUID] = mapped_column(Uuid)
    namespace: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    revision: Mapped[str | None] = mapped_column(Text)
    dimension: Mapped[int] = mapped_column(Integer)
    normalization: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    token: Mapped[UUID | None] = mapped_column(Uuid)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(String(32))
    latency_seconds: Mapped[float | None] = mapped_column(Float)
    runtime: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
