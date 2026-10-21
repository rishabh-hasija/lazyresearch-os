"""Relational mission identity/provenance; bounded versioned payloads use JSONB."""

from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from lazyresearch.infrastructure.persistence.models import Base


class TopicRow(Base):
    __tablename__ = "research_topic"
    __table_args__ = (UniqueConstraint("owner_id", "id"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    current_result_id: Mapped[UUID | None] = mapped_column(Uuid)
    next_run: Mapped[int] = mapped_column(Integer, default=1)
    next_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MissionRow(Base):
    __tablename__ = "research_mission"
    __table_args__ = (
        UniqueConstraint("owner_id", "id"),
        UniqueConstraint("owner_id", "topic_id", "id"),
        UniqueConstraint("topic_id", "run_sequence"),
        ForeignKeyConstraint(
            ["owner_id", "topic_id"], ["research_topic.owner_id", "research_topic.id"]
        ),
        CheckConstraint(
            "status IN ('QUEUED','RUNNING','COMPLETED','PARTIAL','FAILED','CANCELLED')",
            name="mission_status",
        ),
        CheckConstraint("run_sequence > 0", name="mission_run_sequence"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid)
    topic_id: Mapped[UUID] = mapped_column(Uuid)
    question: Mapped[str] = mapped_column(Text)
    run_sequence: Mapped[int] = mapped_column(Integer)
    baseline_result_id: Mapped[UUID | None] = mapped_column(Uuid)
    inputs: Mapped[dict[str, object]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text, default="QUEUED")
    stage: Mapped[str] = mapped_column(Text, default="mission_created")
    dispatched: Mapped[bool] = mapped_column(default=False)
    frozen: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure: Mapped[str | None] = mapped_column(Text)


class MissionStageRow(Base):
    __tablename__ = "research_stage"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "mission_id"], ["research_mission.owner_id", "research_mission.id"]
        ),
    )
    mission_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(Text, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MissionEvidenceRow(Base):
    __tablename__ = "research_evidence"
    __table_args__ = (
        UniqueConstraint("owner_id", "mission_id", "id"),
        UniqueConstraint("mission_id", "chunk_id"),
        ForeignKeyConstraint(
            ["owner_id", "mission_id"], ["research_mission.owner_id", "research_mission.id"]
        ),
        ForeignKeyConstraint(
            ["owner_id", "content_id", "extraction_id"],
            [
                "content_extraction.owner_id",
                "content_extraction.content_id",
                "content_extraction.id",
            ],
        ),
        ForeignKeyConstraint(
            ["owner_id", "chunk_id"], ["content_chunk.owner_id", "content_chunk.id"]
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid)
    mission_id: Mapped[UUID] = mapped_column(Uuid)
    content_id: Mapped[UUID] = mapped_column(Uuid)
    extraction_id: Mapped[UUID] = mapped_column(Uuid)
    chunk_id: Mapped[UUID] = mapped_column(Uuid)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)


class ResultRow(Base):
    __tablename__ = "research_result"
    __table_args__ = (
        UniqueConstraint("owner_id", "topic_id", "id"),
        UniqueConstraint("owner_id", "id"),
        UniqueConstraint("mission_id"),
        UniqueConstraint("topic_id", "version"),
        ForeignKeyConstraint(
            ["owner_id", "topic_id", "mission_id"],
            ["research_mission.owner_id", "research_mission.topic_id", "research_mission.id"],
        ),
        CheckConstraint("version > 0", name="result_version"),
        CheckConstraint("coverage IN ('COMPLETE','PARTIAL')", name="result_coverage"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid)
    topic_id: Mapped[UUID] = mapped_column(Uuid)
    mission_id: Mapped[UUID] = mapped_column(Uuid)
    version: Mapped[int] = mapped_column(Integer)
    run_sequence: Mapped[int] = mapped_column(Integer)
    baseline_result_id: Mapped[UUID | None] = mapped_column(Uuid)
    coverage: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResearchProposalRow(Base):
    __tablename__ = "research_proposal"
    __table_args__ = (
        UniqueConstraint("result_id", "ordinal"),
        ForeignKeyConstraint(
            ["owner_id", "result_id"], ["research_result.owner_id", "research_result.id"]
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid)
    result_id: Mapped[UUID] = mapped_column(Uuid)
    ordinal: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)


# Named, deferred circular links preserve owner/topic scope without changing old migrations.
cast(Table, TopicRow.__table__).append_constraint(
    ForeignKeyConstraint(
        ["owner_id", "id", "current_result_id"],
        ["research_result.owner_id", "research_result.topic_id", "research_result.id"],
        name="fk_topic_current_result",
        use_alter=True,
        deferrable=True,
        initially="DEFERRED",
    )
)
cast(Table, MissionRow.__table__).append_constraint(
    ForeignKeyConstraint(
        ["owner_id", "topic_id", "baseline_result_id"],
        ["research_result.owner_id", "research_result.topic_id", "research_result.id"],
        name="fk_mission_baseline",
        use_alter=True,
        deferrable=True,
        initially="DEFERRED",
    )
)
