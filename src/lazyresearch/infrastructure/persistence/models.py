"""Durable intake and source analysis storage; no research runtime or partner SDKs."""

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class OwnerRow(Base):
    __tablename__ = "owner_scope"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)


class BatchRow(Base):
    __tablename__ = "intake_batch"
    __table_args__ = (
        UniqueConstraint("owner_id", "request_key"),
        UniqueConstraint("owner_id", "id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("owner_scope.id"))
    request_key: Mapped[str] = mapped_column(Text)
    input_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContentRow(Base):
    __tablename__ = "content_item"
    __table_args__ = (
        UniqueConstraint("owner_id", "id"),
        UniqueConstraint("owner_id", "source_type", "source_key", "raw_content_hash"),
        ForeignKeyConstraint(
            ["owner_id", "predecessor_id"], ["content_item.owner_id", "content_item.id"]
        ),
        CheckConstraint(
            "source_type IN ('URL','PDF','TEXT','MARKDOWN')", name="content_source_type"
        ),
        CheckConstraint(
            "predecessor_id IS NULL OR predecessor_id <> id", name="content_predecessor"
        ),
        CheckConstraint(
            "encode(sha256(raw_content),'hex') = raw_content_hash", name="content_hash"
        ),
        Index("ix_content_source_history", "owner_id", "source_type", "source_key", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("owner_scope.id"))
    source_type: Mapped[str] = mapped_column(String(16))
    source_key: Mapped[str] = mapped_column(String(64))
    raw_content: Mapped[bytes] = mapped_column(LargeBinary)
    raw_content_hash: Mapped[str] = mapped_column(String(64))
    original_title: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(Text)
    original_url: Mapped[str | None] = mapped_column(Text)
    canonical_url: Mapped[str | None] = mapped_column(Text)
    source_external_id: Mapped[str | None] = mapped_column(Text)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    predecessor_id: Mapped[UUID | None] = mapped_column(Uuid)
    content_type: Mapped[str] = mapped_column(Text)
    http_status: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )


class EntryRow(Base):
    __tablename__ = "intake_entry"
    __table_args__ = (
        UniqueConstraint("owner_id", "id"),
        UniqueConstraint("batch_id", "ordinal"),
        ForeignKeyConstraint(
            ["owner_id", "batch_id"], ["intake_batch.owner_id", "intake_batch.id"]
        ),
        ForeignKeyConstraint(
            ["owner_id", "content_id"], ["content_item.owner_id", "content_item.id"]
        ),
        CheckConstraint("state IN ('QUEUED','FETCHING','SAVED','FAILED')", name="entry_state"),
        CheckConstraint(
            "(state='FETCHING') = (lease_token IS NOT NULL AND lease_until IS NOT NULL)",
            name="entry_lease",
        ),
        CheckConstraint("(state='SAVED') = (content_id IS NOT NULL)", name="entry_saved"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid)
    batch_id: Mapped[UUID] = mapped_column(Uuid)
    ordinal: Mapped[int] = mapped_column(Integer)
    source_type: Mapped[str] = mapped_column(String(16))
    payload: Mapped[bytes | None] = mapped_column(LargeBinary)
    url: Mapped[str | None] = mapped_column(Text)
    filename: Mapped[str | None] = mapped_column(Text)
    content_type: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(16), default="QUEUED")
    content_id: Mapped[UUID | None] = mapped_column(Uuid)
    duplicate: Mapped[bool] = mapped_column(default=False)
    error_code: Mapped[str | None] = mapped_column(String(40))
    http_status: Mapped[int | None] = mapped_column(Integer)
    lease_token: Mapped[UUID | None] = mapped_column(Uuid)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CaptureRow(Base):
    __tablename__ = "capture_occurrence"
    __table_args__ = (
        UniqueConstraint("owner_id", "intake_reference"),
        UniqueConstraint("owner_id", "entry_id"),
        ForeignKeyConstraint(
            ["owner_id", "content_id"], ["content_item.owner_id", "content_item.id"]
        ),
        ForeignKeyConstraint(
            ["owner_id", "entry_id"], ["intake_entry.owner_id", "intake_entry.id"]
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid)
    content_id: Mapped[UUID] = mapped_column(Uuid)
    entry_id: Mapped[UUID | None] = mapped_column(Uuid)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    intake_reference: Mapped[str] = mapped_column(Text)
    submitted_url: Mapped[str | None] = mapped_column(Text)
    submitted_filename: Mapped[str | None] = mapped_column(Text)
    final_url: Mapped[str | None] = mapped_column(Text)
    content_type: Mapped[str | None] = mapped_column(Text)
    http_status: Mapped[int | None] = mapped_column(Integer)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )


class ExtractionRow(Base):
    __tablename__ = "content_extraction"
    __table_args__ = (
        UniqueConstraint("owner_id", "id"),
        UniqueConstraint("owner_id", "content_id", "id"),
        UniqueConstraint("owner_id", "content_id", "version"),
        ForeignKeyConstraint(
            ["owner_id", "content_id"], ["content_item.owner_id", "content_item.id"]
        ),
        CheckConstraint("status IN ('SUCCEEDED','FAILED','UNAVAILABLE')", name="extraction_status"),
        CheckConstraint(
            "(status='SUCCEEDED') = (normalized_hash IS NOT NULL)", name="extraction_hash_present"
        ),
        CheckConstraint(
            "normalized_hash IS NULL OR "
            "encode(sha256(convert_to(text,'UTF8')),'hex')=normalized_hash",
            name="extraction_hash",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid)
    content_id: Mapped[UUID] = mapped_column(Uuid)
    version: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    normalized_hash: Mapped[str | None] = mapped_column(String(64))
    pages: Mapped[list[dict[str, int]]] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class JobRow(Base):
    __tablename__ = "processing_job"
    __table_args__ = (
        UniqueConstraint("owner_id", "id", "content_id", "extraction_id", name="uq_job_input"),
        UniqueConstraint("owner_id", "content_id", "kind", "version"),
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
        CheckConstraint("kind IN ('EXTRACT','ANALYZE')", name="job_kind"),
        CheckConstraint(
            "(kind='EXTRACT' AND extraction_id IS NULL) OR "
            "(kind='ANALYZE' AND extraction_id IS NOT NULL)",
            name="job_input",
        ),
        CheckConstraint(
            "status IN ('PENDING','RUNNING','SUCCEEDED','FAILED','CANCELLED')", name="job_status"
        ),
        CheckConstraint(
            "(status='RUNNING') = (lease_token IS NOT NULL AND lease_until IS NOT NULL)",
            name="job_lease",
        ),
        CheckConstraint("attempts >= 0", name="job_attempts"),
        Index("ix_processing_claim", "owner_id", "kind", "status", "lease_until"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid)
    content_id: Mapped[UUID] = mapped_column(Uuid)
    extraction_id: Mapped[UUID | None] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(String(16))
    version: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_token: Mapped[UUID | None] = mapped_column(Uuid)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProcessingRunRow(Base):
    __tablename__ = "processing_run"
    __table_args__ = (
        UniqueConstraint("owner_id", "id", "content_id", "extraction_id", name="uq_run_input"),
        UniqueConstraint("job_id", "attempt"),
        UniqueConstraint("lease_token"),
        ForeignKeyConstraint(
            ["owner_id", "job_id", "content_id", "extraction_id"],
            [
                "processing_job.owner_id",
                "processing_job.id",
                "processing_job.content_id",
                "processing_job.extraction_id",
            ],
        ),
        CheckConstraint("attempt > 0", name="run_attempt"),
        CheckConstraint(
            "status IN ('RUNNING','SUCCEEDED','FAILED','CANCELLED')", name="run_status"
        ),
        CheckConstraint("(status='RUNNING') = (ended_at IS NULL)", name="run_ended"),
        CheckConstraint("latency_seconds IS NULL OR latency_seconds >= 0", name="run_latency"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid)
    job_id: Mapped[UUID] = mapped_column(Uuid)
    content_id: Mapped[UUID] = mapped_column(Uuid)
    extraction_id: Mapped[UUID] = mapped_column(Uuid)
    lease_token: Mapped[UUID] = mapped_column(Uuid)
    attempt: Mapped[int] = mapped_column(Integer)
    config_hash: Mapped[str] = mapped_column(String(64), index=True)
    provider: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    model_revision: Mapped[str | None] = mapped_column(Text)
    provider_revision: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(Text)
    prompt_hash: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[str] = mapped_column(Text)
    pipeline_version: Mapped[str] = mapped_column(Text)
    input_hash: Mapped[str] = mapped_column(String(64))
    parameters: Mapped[dict[str, int | float]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latency_seconds: Mapped[float | None] = mapped_column(Float)
    error_code: Mapped[str | None] = mapped_column(String(40))
    calls: Mapped[list[dict[str, object]]] = mapped_column(JSONB)


class ContentAnalysisRow(Base):
    __tablename__ = "content_analysis"
    __table_args__ = (
        UniqueConstraint("owner_id", "id", "content_id", "extraction_id", name="uq_analysis_input"),
        UniqueConstraint("owner_id", "id", name="uq_analysis_owner"),
        UniqueConstraint("job_id"),
        UniqueConstraint("run_id"),
        ForeignKeyConstraint(
            ["owner_id", "run_id", "content_id", "extraction_id"],
            [
                "processing_run.owner_id",
                "processing_run.id",
                "processing_run.content_id",
                "processing_run.extraction_id",
            ],
        ),
        ForeignKeyConstraint(
            ["owner_id", "job_id", "content_id", "extraction_id"],
            [
                "processing_job.owner_id",
                "processing_job.id",
                "processing_job.content_id",
                "processing_job.extraction_id",
            ],
        ),
        CheckConstraint("coverage IN ('COMPLETE','PARTIAL')", name="analysis_coverage"),
        CheckConstraint("total_chars > 0", name="analysis_chars"),
        CheckConstraint(
            "actionability IN ('action_required','no_action','uncertain',"
            "'insufficient_information')",
            name="analysis_actionability",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid)
    content_id: Mapped[UUID] = mapped_column(Uuid)
    extraction_id: Mapped[UUID] = mapped_column(Uuid)
    run_id: Mapped[UUID] = mapped_column(Uuid)
    job_id: Mapped[UUID] = mapped_column(Uuid)
    version: Mapped[str] = mapped_column(Text)
    summaries: Mapped[list[str]] = mapped_column(JSONB)
    topics: Mapped[list[str]] = mapped_column(JSONB)
    claims: Mapped[list[dict[str, str]]] = mapped_column(JSONB)
    entities: Mapped[list[dict[str, str]]] = mapped_column(JSONB)
    actionability: Mapped[str] = mapped_column(String(32))
    covered_ranges: Mapped[list[list[int]]] = mapped_column(JSONB)
    total_chars: Mapped[int] = mapped_column(Integer)
    coverage: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ActionProposalRow(Base):
    __tablename__ = "action_proposal"
    __table_args__ = (
        UniqueConstraint("owner_id", "analysis_id", "id", name="uq_proposal_origin"),
        UniqueConstraint("owner_id", "analysis_id", "candidate_ordinal"),
        ForeignKeyConstraint(
            ["owner_id", "analysis_id"], ["content_analysis.owner_id", "content_analysis.id"]
        ),
        CheckConstraint("candidate_ordinal >= 0", name="proposal_ordinal"),
        CheckConstraint(
            "uncertainty IN ('unknown','low','medium','high')", name="proposal_uncertainty"
        ),
        CheckConstraint(
            "kind IN ('task','deadline','follow_up','form','application','renewal',"
            "'decision','purchase','event')",
            name="proposal_kind",
        ),
        CheckConstraint(
            "deadline_date IS NULL OR deadline_raw IS NOT NULL", name="proposal_deadline"
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid)
    analysis_id: Mapped[UUID] = mapped_column(Uuid)
    candidate_ordinal: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(24))
    uncertainty: Mapped[str] = mapped_column(String(16))
    deadline_raw: Mapped[str | None] = mapped_column(Text)
    deadline_date: Mapped[date | None] = mapped_column(Date)


class AnalysisEvidenceRow(Base):
    __tablename__ = "analysis_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "analysis_id", "content_id", "extraction_id"],
            [
                "content_analysis.owner_id",
                "content_analysis.id",
                "content_analysis.content_id",
                "content_analysis.extraction_id",
            ],
        ),
        ForeignKeyConstraint(
            ["owner_id", "analysis_id", "proposal_id"],
            ["action_proposal.owner_id", "action_proposal.analysis_id", "action_proposal.id"],
        ),
        CheckConstraint("role IN ('CLAIM','ENTITY','ACTION')", name="evidence_role"),
        CheckConstraint("(role='ACTION') = (proposal_id IS NOT NULL)", name="evidence_proposal"),
        CheckConstraint(
            '"end" > start AND start >= 0 AND ordinal >= 0 AND evidence_ordinal >= 0',
            name="evidence_span",
        ),
        UniqueConstraint("analysis_id", "role", "ordinal", "evidence_ordinal"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid)
    analysis_id: Mapped[UUID] = mapped_column(Uuid)
    content_id: Mapped[UUID] = mapped_column(Uuid)
    extraction_id: Mapped[UUID] = mapped_column(Uuid)
    role: Mapped[str] = mapped_column(String(16))
    ordinal: Mapped[int] = mapped_column(Integer)
    evidence_ordinal: Mapped[int] = mapped_column(Integer)
    proposal_id: Mapped[UUID | None] = mapped_column(Uuid)
    start: Mapped[int] = mapped_column(Integer)
    end: Mapped[int] = mapped_column(Integer)
    page: Mapped[int | None] = mapped_column(Integer)
    quote: Mapped[str] = mapped_column(Text)
