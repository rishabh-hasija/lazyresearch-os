"""Append-only ranking snapshots and interactions, owner/content scope in every FK."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from lazyresearch.infrastructure.persistence.models import Base


class RankingObservationRow(Base):
    __tablename__ = "ranking_observation"
    __table_args__ = (
        UniqueConstraint("owner_id", "content_id", "id"),
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
        ForeignKeyConstraint(
            ["owner_id", "analysis_id"], ["content_analysis.owner_id", "content_analysis.id"]
        ),
        CheckConstraint("cutoff <= recorded_at", name="ranking_cutoff"),
        Index("ix_ranking_owner_content", "owner_id", "content_id", "cutoff"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid)
    content_id: Mapped[UUID] = mapped_column(Uuid)
    extraction_id: Mapped[UUID | None] = mapped_column(Uuid)
    analysis_id: Mapped[UUID | None] = mapped_column(Uuid)
    cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )


class InteractionRow(Base):
    __tablename__ = "user_interaction"
    __table_args__ = (
        UniqueConstraint("owner_id", "content_id", "id"),
        UniqueConstraint("supersedes"),
        ForeignKeyConstraint(
            ["owner_id", "content_id"], ["content_item.owner_id", "content_item.id"]
        ),
        ForeignKeyConstraint(
            ["owner_id", "content_id", "observation_id"],
            [
                "ranking_observation.owner_id",
                "ranking_observation.content_id",
                "ranking_observation.id",
            ],
        ),
        ForeignKeyConstraint(
            ["owner_id", "content_id", "supersedes"],
            ["user_interaction.owner_id", "user_interaction.content_id", "user_interaction.id"],
        ),
        CheckConstraint(
            "kind IN ('ITEM_OPENED','ITEM_IGNORED','ITEM_ARCHIVED','ITEM_SAVED',"
            "'ITEM_ACTED_ON','ITEM_RESURFACED','MISSION_USED_ITEM','FEEDBACK_LABELED')",
            name="interaction_kind",
        ),
        CheckConstraint(
            "label IS NULL OR label IN ('READ','KEEP','ACT','IGNORE')", name="interaction_label"
        ),
        CheckConstraint(
            "(kind='FEEDBACK_LABELED') = (label IS NOT NULL)", name="interaction_target"
        ),
        CheckConstraint(
            "label IS NULL OR (explicit AND observation_id IS NOT NULL)",
            name="interaction_explicit",
        ),
        CheckConstraint(
            "supersedes IS NULL OR (label IS NOT NULL AND supersedes<>id)",
            name="interaction_supersedes",
        ),
        CheckConstraint("occurred_at <= recorded_at", name="interaction_time"),
        Index("ix_interaction_owner_content", "owner_id", "content_id", "recorded_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid)
    content_id: Mapped[UUID] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(Text)
    explicit: Mapped[bool]
    observation_id: Mapped[UUID | None] = mapped_column(Uuid)
    label: Mapped[str | None] = mapped_column(Text)
    supersedes: Mapped[UUID | None] = mapped_column(Uuid)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
