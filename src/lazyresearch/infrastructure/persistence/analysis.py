"""Fenced analysis attempts and append-only artifacts in short PostgreSQL transactions."""

from dataclasses import asdict
from datetime import date, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import Engine, and_, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from lazyresearch.application.analysis_models import AnalysisConfig, AnalysisWork, CallAttempt
from lazyresearch.application.intake_models import (
    ContentExtraction,
    ExtractionData,
    ExtractionStatus,
    PageSpan,
    ProcessingLease,
)
from lazyresearch.domain.actions import ActionOrigin, ActionOriginType, ActionProposal, Deadline
from lazyresearch.domain.analysis import CitedStatement, ContentAnalysis
from lazyresearch.domain.content import SourceEvidence
from lazyresearch.domain.identity import AnalysisId, ContentId, ExtractionId, OwnerId, ProposalId
from lazyresearch.domain.processing import ProcessingIdentity
from lazyresearch.infrastructure.persistence.models import (
    ActionProposalRow,
    AnalysisEvidenceRow,
    ContentAnalysisRow,
    ExtractionRow,
    JobRow,
    ProcessingRunRow,
)
from lazyresearch.infrastructure.persistence.repositories import (
    DatabaseAdapter,
    SQLAlchemyProcessingRepository,
)
from lazyresearch.ports.errors import RepositoryConflict


def processing_value(row: ProcessingRunRow) -> ProcessingIdentity:
    return ProcessingIdentity(
        **{name: getattr(row, name) for name in ProcessingIdentity.__dataclass_fields__}
    )


class SQLAlchemyAnalysisStore(DatabaseAdapter):
    def __init__(self, engine: Engine) -> None:
        super().__init__(engine)

    def claim(self, owner_id: OwnerId, config: AnalysisConfig) -> AnalysisWork | None:
        prefix = f"ai:{config.fingerprint}:"
        with self.transaction() as s:
            # Materialize a configuration-specific operation for each immutable successful input.
            # Existing extraction-version ANALYZE rows are dispatch placeholders from Task 1B.
            for candidate_input in s.scalars(
                select(ExtractionRow)
                .where(ExtractionRow.owner_id == owner_id, ExtractionRow.status == "SUCCEEDED")
                .order_by(ExtractionRow.id)
            ):
                s.execute(
                    insert(JobRow)
                    .values(
                        id=uuid4(),
                        owner_id=owner_id,
                        content_id=candidate_input.content_id,
                        extraction_id=candidate_input.id,
                        kind="ANALYZE",
                        version=prefix + str(candidate_input.id),
                        status="PENDING",
                        attempts=0,
                    )
                    .on_conflict_do_nothing(
                        index_elements=["owner_id", "content_id", "kind", "version"]
                    )
                )
                placeholder = s.scalar(
                    select(JobRow)
                    .where(
                        JobRow.owner_id == owner_id,
                        JobRow.content_id == candidate_input.content_id,
                        JobRow.kind == "ANALYZE",
                        JobRow.version == candidate_input.version,
                        JobRow.status == "PENDING",
                    )
                    .with_for_update(skip_locked=True)
                )
                if placeholder is not None:
                    placeholder.status = "CANCELLED"
            job = s.scalar(
                select(JobRow)
                .where(
                    JobRow.owner_id == owner_id,
                    JobRow.kind == "ANALYZE",
                    JobRow.version.startswith(prefix),
                    or_(
                        JobRow.status == "PENDING",
                        and_(
                            JobRow.status == "RUNNING", JobRow.lease_until <= func.clock_timestamp()
                        ),
                    ),
                )
                # A newly saved extraction must not wait behind configuration refreshes
                # of sources that already have a usable analysis.
                .order_by(
                    exists(
                        select(ContentAnalysisRow.id).where(
                            ContentAnalysisRow.owner_id == JobRow.owner_id,
                            ContentAnalysisRow.content_id == JobRow.content_id,
                            ContentAnalysisRow.extraction_id == JobRow.extraction_id,
                        )
                    ),
                    JobRow.created_at,
                    JobRow.id,
                )
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if job is None:
                return None
            extraction = s.scalar(
                select(ExtractionRow).where(
                    ExtractionRow.owner_id == owner_id,
                    ExtractionRow.id == job.extraction_id,
                    ExtractionRow.content_id == job.content_id,
                    ExtractionRow.status == "SUCCEEDED",
                )
            )
            if extraction is None or extraction.normalized_hash is None:
                raise RepositoryConflict("analysis input is unavailable")
            now = s.scalar(select(func.clock_timestamp()))
            assert isinstance(now, datetime)
            for abandoned in s.scalars(
                select(ProcessingRunRow).where(
                    ProcessingRunRow.job_id == job.id, ProcessingRunRow.status == "RUNNING"
                )
            ):
                self._end(abandoned, "FAILED", "LEASE_EXPIRED", now, ())
            job.status, job.lease_token = "RUNNING", uuid4()
            job.attempts += 1
            job.lease_until = now + timedelta(seconds=2 * config.timeout_seconds + 30)
            identity = config.identity(extraction.normalized_hash)
            run = ProcessingRunRow(
                id=uuid4(),
                owner_id=owner_id,
                job_id=job.id,
                content_id=job.content_id,
                extraction_id=extraction.id,
                lease_token=job.lease_token,
                attempt=job.attempts,
                config_hash=config.fingerprint,
                **asdict(identity),
                parameters=config.parameters,
                status="RUNNING",
                started_at=now,
                calls=[],
            )
            s.add(run)
            return AnalysisWork(
                lease=ProcessingLease(
                    id=job.id,
                    owner_id=owner_id,
                    content_id=ContentId(job.content_id),
                    extraction_id=extraction.id,
                    kind="ANALYZE",
                    version=job.version,
                    token=job.lease_token,
                    expires_at=job.lease_until,
                ),
                run_id=run.id,
                processing=identity,
                extraction=ContentExtraction(
                    id=extraction.id,
                    owner_id=owner_id,
                    content_id=ContentId(extraction.content_id),
                    data=ExtractionData(
                        status=ExtractionStatus.SUCCEEDED,
                        version=extraction.version,
                        text=extraction.text,
                        normalized_hash=extraction.normalized_hash,
                        pages=tuple(PageSpan(**p) for p in extraction.pages),
                    ),
                ),
            )

    def pending_sources(self, owner_id: OwnerId, config: AnalysisConfig) -> int:
        with self.transaction() as s:
            count = s.scalar(
                select(func.count(func.distinct(JobRow.content_id))).where(
                    JobRow.owner_id == owner_id,
                    JobRow.kind == "ANALYZE",
                    JobRow.version.startswith(f"ai:{config.fingerprint}:"),
                    JobRow.status.in_(("PENDING", "RUNNING")),
                )
            )
            return int(count or 0)

    def renew(self, work: AnalysisWork) -> None:
        with self.transaction() as s:
            job, run = self._active(s, work)
            now = s.scalar(select(func.clock_timestamp()))
            assert isinstance(now, datetime)
            job.lease_until = now + timedelta(seconds=2 * run.parameters["timeout_seconds"] + 30)

    @staticmethod
    def _active(s: Session, work: AnalysisWork) -> tuple[JobRow, ProcessingRunRow]:
        job = SQLAlchemyProcessingRepository.leased_job(s, work.lease)
        run = s.scalar(
            select(ProcessingRunRow)
            .where(
                ProcessingRunRow.owner_id == work.lease.owner_id,
                ProcessingRunRow.id == work.run_id,
                ProcessingRunRow.job_id == job.id,
                ProcessingRunRow.lease_token == work.lease.token,
                ProcessingRunRow.status == "RUNNING",
            )
            .with_for_update()
        )
        if run is None or processing_value(run) != work.processing:
            raise RepositoryConflict("analysis run identity changed")
        return job, run

    @staticmethod
    def _end(
        run: ProcessingRunRow,
        status: str,
        error: str | None,
        now: datetime,
        attempts: tuple[CallAttempt, ...],
    ) -> None:
        run.status, run.error_code, run.ended_at = status, error, now
        run.latency_seconds = max(0, (now - run.started_at).total_seconds())
        run.calls = [
            {
                "started_at": a.started_at.isoformat(),
                "ended_at": a.ended_at.isoformat(),
                "latency_seconds": a.latency_seconds,
                "outcome": a.outcome,
                "repair": a.repair,
            }
            for a in attempts
        ]

    def fail(self, work: AnalysisWork, error: str, attempts: tuple[CallAttempt, ...]) -> None:
        if error not in {
            "TIMEOUT",
            "UNAVAILABLE",
            "INVALID_RESPONSE",
            "INVALID_SCHEMA",
            "INVALID_LOCATOR",
            "MODEL_CHANGED",
        }:
            raise ValueError("unknown sanitized AI failure")
        with self.transaction() as s:
            job, run = self._active(s, work)
            now = s.scalar(select(func.clock_timestamp()))
            assert isinstance(now, datetime)
            self._end(run, "FAILED", error, now, attempts)
            job.status, job.lease_token, job.lease_until = "FAILED", None, None

    def publish(
        self, work: AnalysisWork, analysis: ContentAnalysis, attempts: tuple[CallAttempt, ...]
    ) -> None:
        if (
            analysis.owner_id,
            analysis.content_id,
            analysis.extraction_id,
            analysis.run_id,
            analysis.version,
            analysis.processing,
        ) != (
            work.lease.owner_id,
            work.lease.content_id,
            work.extraction.id,
            work.run_id,
            work.lease.version,
            work.processing,
        ):
            raise RepositoryConflict("analysis differs from claimed operation")
        with self.transaction() as s:
            job, run = self._active(s, work)
            extraction = s.get(ExtractionRow, analysis.extraction_id)
            if (
                extraction is None
                or extraction.owner_id != analysis.owner_id
                or extraction.normalized_hash != analysis.processing.input_hash
                or len(extraction.text) != analysis.total_chars
            ):
                raise RepositoryConflict("analysis input differs from immutable extraction")
            row = ContentAnalysisRow(
                id=analysis.id,
                owner_id=analysis.owner_id,
                content_id=analysis.content_id,
                extraction_id=analysis.extraction_id,
                run_id=run.id,
                job_id=job.id,
                version=analysis.version,
                summaries=list(analysis.summaries),
                topics=list(analysis.topics),
                claims=[
                    {
                        "text": c.text,
                        "uncertainty": c.uncertainty,
                        "support_review": c.support_review,
                    }
                    for c in analysis.claims
                ],
                entities=[
                    {
                        "text": e.text,
                        "uncertainty": e.uncertainty,
                        "support_review": e.support_review,
                    }
                    for e in analysis.entities
                ],
                actionability=analysis.actionability,
                covered_ranges=[list(r) for r in analysis.covered_ranges],
                total_chars=analysis.total_chars,
                coverage=analysis.coverage,
            )
            s.add(row)
            s.flush()
            for proposal in analysis.proposals:
                # This slice produces only conservative date-only values, never guessed instants.
                normalized = proposal.deadline.normalized
                if normalized is not None and type(normalized) is not date:
                    raise RepositoryConflict("source analysis only normalizes explicit dates")
                s.add(
                    ActionProposalRow(
                        id=proposal.id,
                        owner_id=analysis.owner_id,
                        analysis_id=analysis.id,
                        candidate_ordinal=proposal.candidate_ordinal,
                        title=proposal.title,
                        description=proposal.description,
                        kind=proposal.kind,
                        uncertainty=proposal.uncertainty,
                        deadline_raw=proposal.deadline.raw_text,
                        deadline_date=normalized,
                    )
                )
            s.flush()
            groups: list[tuple[str, int, UUID | None, tuple[SourceEvidence, ...]]] = [
                ("CLAIM", i, None, c.evidence) for i, c in enumerate(analysis.claims)
            ]
            groups += [("ENTITY", i, None, e.evidence) for i, e in enumerate(analysis.entities)]
            groups += [
                ("ACTION", p.candidate_ordinal, p.id, p.evidence) for p in analysis.proposals
            ]
            for role, ordinal, proposal_id, evidence in groups:
                for index, source in enumerate(evidence):
                    if (
                        source.owner_id != analysis.owner_id
                        or source.content_id != analysis.content_id
                        or source.extraction_id != analysis.extraction_id
                        or not any(
                            start <= source.start < source.end <= end
                            for start, end in analysis.covered_ranges
                        )
                        or extraction.text[source.start : source.end] != source.quote
                    ):
                        raise RepositoryConflict("evidence does not match processed input")
                    s.add(
                        AnalysisEvidenceRow(
                            owner_id=source.owner_id,
                            analysis_id=analysis.id,
                            content_id=source.content_id,
                            extraction_id=source.extraction_id,
                            role=role,
                            ordinal=ordinal,
                            evidence_ordinal=index,
                            proposal_id=proposal_id,
                            start=source.start,
                            end=source.end,
                            page=source.page,
                            quote=source.quote,
                        )
                    )
            now = s.scalar(select(func.clock_timestamp()))
            assert isinstance(now, datetime)
            self._end(run, "SUCCEEDED", None, now, attempts)
            job.status, job.lease_token, job.lease_until = "SUCCEEDED", None, None

    def retry_failed(self, owner_id: OwnerId, job_id: UUID) -> None:
        with self.transaction() as s:
            job = s.scalar(
                select(JobRow)
                .where(
                    JobRow.owner_id == owner_id,
                    JobRow.id == job_id,
                    JobRow.kind == "ANALYZE",
                    JobRow.version.startswith("ai:"),
                    JobRow.status == "FAILED",
                )
                .with_for_update()
            )
            if job is None:
                raise RepositoryConflict(
                    "only failed analysis operations can be explicitly retried"
                )
            job.status = "PENDING"

    def cancel(self, owner_id: OwnerId, job_id: UUID) -> None:
        with self.transaction() as s:
            job = s.scalar(
                select(JobRow)
                .where(
                    JobRow.owner_id == owner_id,
                    JobRow.id == job_id,
                    JobRow.kind == "ANALYZE",
                    JobRow.version.startswith("ai:"),
                    JobRow.status.in_(["PENDING", "RUNNING"]),
                )
                .with_for_update()
            )
            if job is None:
                raise RepositoryConflict("operation cannot be cancelled")
            now = s.scalar(select(func.clock_timestamp()))
            assert isinstance(now, datetime)
            for run in s.scalars(
                select(ProcessingRunRow).where(
                    ProcessingRunRow.job_id == job.id, ProcessingRunRow.status == "RUNNING"
                )
            ):
                self._end(run, "CANCELLED", "CANCELLED", now, ())
            job.status, job.lease_token, job.lease_until = "CANCELLED", None, None

    def get(self, owner_id: OwnerId, analysis_id: UUID) -> ContentAnalysis | None:
        with self.transaction() as s:
            row = s.scalar(
                select(ContentAnalysisRow).where(
                    ContentAnalysisRow.owner_id == owner_id, ContentAnalysisRow.id == analysis_id
                )
            )
            if row is None:
                return None
            run = s.get(ProcessingRunRow, row.run_id)
            assert run is not None
            processing = processing_value(run)
            evidence_rows = list(
                s.scalars(
                    select(AnalysisEvidenceRow)
                    .where(
                        AnalysisEvidenceRow.owner_id == owner_id,
                        AnalysisEvidenceRow.analysis_id == row.id,
                    )
                    .order_by(AnalysisEvidenceRow.evidence_ordinal)
                )
            )

            def evidence(role: str, ordinal: int) -> tuple[SourceEvidence, ...]:
                return tuple(
                    SourceEvidence(
                        owner_id=owner_id,
                        content_id=ContentId(e.content_id),
                        extraction_id=ExtractionId(e.extraction_id),
                        start=e.start,
                        end=e.end,
                        quote=e.quote,
                        page=e.page,
                    )
                    for e in evidence_rows
                    if e.role == role and e.ordinal == ordinal
                )

            def statements(role: str, values: list[dict[str, str]]) -> tuple[CitedStatement, ...]:
                return tuple(
                    CitedStatement(
                        text=c["text"],
                        uncertainty=c["uncertainty"],
                        support_review=c["support_review"],
                        evidence=evidence(role, i),
                    )
                    for i, c in enumerate(values)
                )

            proposals = tuple(
                ActionProposal(
                    id=ProposalId(p.id),
                    owner_id=owner_id,
                    title=p.title,
                    description=p.description,
                    kind=p.kind,
                    uncertainty=p.uncertainty,
                    candidate_ordinal=p.candidate_ordinal,
                    processing=processing,
                    origin=ActionOrigin(
                        kind=ActionOriginType.SOURCE_ANALYSIS, analysis_id=AnalysisId(row.id)
                    ),
                    deadline=Deadline(raw_text=p.deadline_raw, normalized=p.deadline_date),
                    evidence=evidence("ACTION", p.candidate_ordinal),
                )
                for p in s.scalars(
                    select(ActionProposalRow)
                    .where(
                        ActionProposalRow.owner_id == owner_id,
                        ActionProposalRow.analysis_id == row.id,
                    )
                    .order_by(ActionProposalRow.candidate_ordinal)
                )
            )
            return ContentAnalysis(
                id=AnalysisId(row.id),
                owner_id=owner_id,
                content_id=ContentId(row.content_id),
                extraction_id=row.extraction_id,
                run_id=row.run_id,
                version=row.version,
                processing=processing,
                summaries=tuple(row.summaries),
                topics=tuple(row.topics),
                claims=statements("CLAIM", row.claims),
                entities=statements("ENTITY", row.entities),
                actionability=row.actionability,
                proposals=proposals,
                covered_ranges=tuple((r[0], r[1]) for r in row.covered_ranges),
                total_chars=row.total_chars,
                coverage=row.coverage,
            )
