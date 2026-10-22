"""Mutable user task state is separate from immutable generated proposals."""

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Integer, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from lazyresearch.infrastructure.persistence.models import Base


class ActionItemRow(Base):
    __tablename__ = "action_item"
    __table_args__ = (
        UniqueConstraint("owner_id", "id"),
        UniqueConstraint("owner_id", "proposal_id"),
        ForeignKeyConstraint(
            ["owner_id", "analysis_id"], ["content_analysis.owner_id", "content_analysis.id"]
        ),
        ForeignKeyConstraint(
            ["owner_id", "result_id"], ["research_result.owner_id", "research_result.id"]
        ),
        CheckConstraint("(analysis_id IS NULL) <> (result_id IS NULL)", name="task_origin"),
        CheckConstraint(
            "status IN ('PROPOSED','ACCEPTED','COMPLETED','DISMISSED')", name="task_status"
        ),
        CheckConstraint("revision >= 0", name="task_revision"),
        CheckConstraint("length(trim(title))>0 AND length(trim(description))>0", name="task_text"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid)
    proposal_id: Mapped[UUID] = mapped_column(Uuid)
    analysis_id: Mapped[UUID | None] = mapped_column(Uuid)
    result_id: Mapped[UUID | None] = mapped_column(Uuid)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    deadline_raw: Mapped[str | None] = mapped_column(Text)
    deadline_normalized: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer)
