"""Owner-scoped UI read projections and optimistic task state persistence."""

import json
from datetime import date, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select

from lazyresearch.application.mission_models import MissionEvidence
from lazyresearch.application.workspace_models import MissionView, ResultView, SourceView
from lazyresearch.domain.actions import (
    ActionItem,
    ActionOrigin,
    ActionOriginType,
    ActionProposal,
    ActionStatus,
    Deadline,
)
from lazyresearch.domain.content import SourceEvidence
from lazyresearch.domain.identity import ActionId, OwnerId, ProposalId, ResultId, TopicId
from lazyresearch.domain.research import ResearchTopic
from lazyresearch.infrastructure.persistence.analysis import SQLAlchemyAnalysisStore
from lazyresearch.infrastructure.persistence.mission_models import (
    MissionRow,
    ResearchProposalRow,
    ResultRow,
    TopicRow,
)
from lazyresearch.infrastructure.persistence.missions import (
    PostgreSQLMissionStore,
    processing_value,
)
from lazyresearch.infrastructure.persistence.models import (
    ActionProposalRow,
    CaptureRow,
    ContentAnalysisRow,
    ContentRow,
    ExtractionRow,
    JobRow,
)
from lazyresearch.infrastructure.persistence.repositories import DatabaseAdapter, lock
from lazyresearch.infrastructure.persistence.retrieval import PostgreSQLRetrievalStore
from lazyresearch.infrastructure.persistence.retrieval_models import (
    CollectionRow,
    RetrievalStateRow,
)
from lazyresearch.infrastructure.persistence.workspace_models import ActionItemRow
from lazyresearch.ports.errors import RepositoryConflict


class PostgreSQLWorkspaceReads(DatabaseAdapter):
    def collections(self, owner: OwnerId) -> tuple[tuple[UUID, str], ...]:
        with self.transaction() as s:
            return tuple(
                (r.id, r.name)
                for r in s.scalars(
                    select(CollectionRow)
                    .where(CollectionRow.owner_id == owner)
                    .order_by(CollectionRow.name)
                    .limit(100)
                )
            )

    def assign_collection(self, owner: OwnerId, collection: UUID, content: UUID) -> None:
        from lazyresearch.domain.identity import ContentId

        PostgreSQLRetrievalStore(self.engine).add_to_collection(
            owner, collection, ContentId(content)
        )

    def source(self, owner: OwnerId, identity: UUID) -> SourceView | None:
        with self.transaction() as s:
            row = s.scalar(
                select(ContentRow).where(ContentRow.owner_id == owner, ContentRow.id == identity)
            )
            state = s.get(RetrievalStateRow, (owner, identity))
            if row is None or (state and state.visibility in {"DELETED", "DELETION_PENDING"}):
                return None
            extraction = s.scalar(
                select(ExtractionRow)
                .where(ExtractionRow.owner_id == owner, ExtractionRow.content_id == identity)
                .order_by(ExtractionRow.created_at.desc(), ExtractionRow.id.desc())
                .limit(1)
            )
            analysis_row = (
                None
                if extraction is None
                else s.scalar(
                    select(ContentAnalysisRow)
                    .where(
                        ContentAnalysisRow.owner_id == owner,
                        ContentAnalysisRow.content_id == identity,
                        ContentAnalysisRow.extraction_id == extraction.id,
                    )
                    .order_by(ContentAnalysisRow.created_at.desc(), ContentAnalysisRow.id.desc())
                    .limit(1)
                )
            )
            analysis = (
                SQLAlchemyAnalysisStore(self.engine).get(owner, analysis_row.id)
                if analysis_row
                else None
            )
            job = s.scalar(
                select(JobRow)
                .where(
                    JobRow.owner_id == owner,
                    JobRow.content_id == identity,
                    JobRow.version.startswith("ai:"),
                )
                .order_by(JobRow.created_at.desc(), JobRow.id.desc())
                .limit(1)
            )
            filename = s.scalar(
                select(CaptureRow.submitted_filename)
                .where(CaptureRow.owner_id == owner, CaptureRow.content_id == identity)
                .order_by(CaptureRow.recorded_at)
                .limit(1)
            )
            return SourceView(
                row.id,
                row.original_title or row.original_url or filename or "Untitled source",
                row.source_type,
                row.captured_at,
                row.original_url,
                extraction.status if extraction else "PENDING",
                extraction.text if extraction else "",
                analysis,
                "READY" if analysis else job.status if job else "PENDING",
                job.id if job and job.status == "FAILED" else None,
            )

    def sources(self, owner: OwnerId) -> tuple[SourceView, ...]:
        with self.transaction() as s:
            identities = tuple(
                s.scalars(
                    select(ContentRow.id)
                    .where(ContentRow.owner_id == owner)
                    .order_by(ContentRow.created_at.desc())
                    .limit(200)
                )
            )
        return tuple(
            v for identity in identities if (v := self.source(owner, identity)) is not None
        )

    def evidence(self, owner: OwnerId, locator: SourceEvidence) -> tuple[str, str | None] | None:
        if locator.owner_id != owner:
            return None
        # Evidence needs the exact historical extraction, title and current visibility;
        # loading the source's newest analysis here multiplies every citation read.
        filename = (
            select(CaptureRow.submitted_filename)
            .where(CaptureRow.owner_id == owner, CaptureRow.content_id == locator.content_id)
            .order_by(CaptureRow.recorded_at)
            .limit(1)
            .scalar_subquery()
        )
        with self.transaction() as s:
            row = s.execute(
                select(
                    func.coalesce(
                        func.nullif(ContentRow.original_title, ""),
                        func.nullif(ContentRow.original_url, ""),
                        func.nullif(filename, ""),
                        "Untitled source",
                    ),
                    ContentRow.original_url,
                    ExtractionRow.text,
                    RetrievalStateRow.visibility,
                )
                .join(
                    ExtractionRow,
                    (ExtractionRow.owner_id == ContentRow.owner_id)
                    & (ExtractionRow.content_id == ContentRow.id),
                )
                .outerjoin(
                    RetrievalStateRow,
                    (RetrievalStateRow.owner_id == ContentRow.owner_id)
                    & (RetrievalStateRow.content_id == ContentRow.id),
                )
                .where(
                    ContentRow.owner_id == owner,
                    ContentRow.id == locator.content_id,
                    ExtractionRow.id == locator.extraction_id,
                )
            ).one_or_none()
            if (
                row is None
                or row[3] in {"DELETED", "DELETION_PENDING"}
                or row[2][locator.start : locator.end] != locator.quote
            ):
                return None
            return row[0], row[1]

    def topics(self, owner: OwnerId) -> tuple[ResearchTopic, ...]:
        with self.transaction() as s:
            ids = tuple(
                s.scalars(
                    select(TopicRow.id)
                    .where(TopicRow.owner_id == owner)
                    .order_by(TopicRow.updated_at.desc())
                    .limit(100)
                )
            )
        store = PostgreSQLMissionStore(self.engine)
        return tuple(
            t for identity in ids if (t := store.get_topic(owner, TopicId(identity))) is not None
        )

    def missions(self, owner: OwnerId, topic: UUID) -> tuple[MissionView, ...]:
        with self.transaction() as s:
            return tuple(
                MissionView(r.id, r.question, r.status, r.stage, r.run_sequence, r.failure)
                for r in s.scalars(
                    select(MissionRow)
                    .where(MissionRow.owner_id == owner, MissionRow.topic_id == topic)
                    .order_by(MissionRow.run_sequence.desc())
                    .limit(50)
                )
            )

    def result(self, owner: OwnerId, identity: UUID) -> ResultView | None:
        with self.transaction() as s:
            row = s.scalar(
                select(ResultRow).where(ResultRow.owner_id == owner, ResultRow.id == identity)
            )
            if row is None:
                return None
            for raw in cast(list[Any], row.payload["evidence"]):
                e = MissionEvidence.model_validate_json(json.dumps(raw))
                if self.evidence(owner, e.locator()) is None:
                    raise RepositoryConflict("result evidence unavailable")
            baseline = s.get(ResultRow, row.baseline_result_id) if row.baseline_result_id else None
            return ResultView(
                row.id,
                row.version,
                row.run_sequence,
                row.created_at,
                row.coverage,
                baseline.version if baseline else None,
                row.payload,
            )

    def results(self, owner: OwnerId, topic: UUID) -> tuple[ResultView, ...]:
        with self.transaction() as s:
            ids = tuple(
                s.scalars(
                    select(ResultRow.id)
                    .where(ResultRow.owner_id == owner, ResultRow.topic_id == topic)
                    .order_by(ResultRow.version.desc())
                    .limit(50)
                )
            )
        return tuple(r for identity in ids if (r := self.result(owner, identity)) is not None)

    def proposal(self, owner: OwnerId, identity: UUID) -> ActionProposal | None:
        with self.transaction() as s:
            source = s.scalar(
                select(ActionProposalRow).where(
                    ActionProposalRow.owner_id == owner, ActionProposalRow.id == identity
                )
            )
            if source is not None:
                analysis = SQLAlchemyAnalysisStore(self.engine).get(owner, source.analysis_id)
                value = (
                    next((p for p in analysis.proposals if p.id == identity), None)
                    if analysis
                    else None
                )
            else:
                research = s.scalar(
                    select(ResearchProposalRow).where(
                        ResearchProposalRow.owner_id == owner, ResearchProposalRow.id == identity
                    )
                )
                if research is None:
                    return None
                p = research.payload
                result = self.result(owner, research.result_id)
                if result is None:
                    return None
                registry = {
                    str(e.id): e
                    for raw in result.payload["evidence"]
                    if (e := MissionEvidence.model_validate_json(json.dumps(raw)))
                }
                action = result.payload["brief"]["action_candidates"][research.ordinal]
                raw_deadline = cast(dict[str, Any], p["deadline"])
                normalized = raw_deadline.get("normalized")
                value = ActionProposal(
                    id=ProposalId(research.id),
                    owner_id=owner,
                    title=str(p["title"]),
                    description=str(p["description"]),
                    candidate_ordinal=research.ordinal,
                    origin=ActionOrigin(
                        kind=ActionOriginType.RESEARCH_RESULT,
                        result_id=ResultId(research.result_id),
                    ),
                    processing=processing_value(cast(dict[str, object], p["processing"])),
                    evidence=tuple(registry[key].locator() for key in action["evidence"]),
                    deadline=Deadline(
                        raw_text=raw_deadline.get("raw_text"),
                        normalized=date.fromisoformat(normalized) if normalized else None,
                    ),
                    uncertainty=str(p["uncertainty"]),
                    kind=str(p["kind"]),
                )
            if value is None or any(self.evidence(owner, e) is None for e in value.evidence):
                return None
            return value

    def proposals(self, owner: OwnerId) -> tuple[ActionProposal, ...]:
        with self.transaction() as s:
            ids = list(
                s.scalars(
                    select(ActionProposalRow.id)
                    .where(ActionProposalRow.owner_id == owner)
                    .limit(100)
                )
            )
            ids += list(
                s.scalars(
                    select(ResearchProposalRow.id)
                    .where(ResearchProposalRow.owner_id == owner)
                    .limit(100)
                )
            )
        return tuple(p for identity in ids if (p := self.proposal(owner, identity)) is not None)

    def retry_analysis(self, owner: OwnerId, job: UUID) -> None:
        SQLAlchemyAnalysisStore(self.engine).retry_failed(owner, job)


def task_value(row: ActionItemRow, proposal: ActionProposal) -> ActionItem:
    normalized = row.deadline_normalized
    deadline = (
        (
            datetime.fromisoformat(normalized)
            if "T" in normalized
            else date.fromisoformat(normalized)
        )
        if normalized
        else None
    )
    return ActionItem(
        id=ActionId(row.id),
        proposal=proposal,
        title=row.title,
        description=row.description,
        deadline=Deadline(raw_text=row.deadline_raw, normalized=deadline),
        status=ActionStatus(row.status),
        revision=row.revision,
    )


class PostgreSQLActionRepository(DatabaseAdapter):
    def get(self, owner_id: OwnerId, action_id: ActionId) -> ActionItem | None:
        with self.transaction() as s:
            row = s.scalar(
                select(ActionItemRow).where(
                    ActionItemRow.owner_id == owner_id, ActionItemRow.id == action_id
                )
            )
            if row is None:
                return None
            proposal = PostgreSQLWorkspaceReads(self.engine).proposal(owner_id, row.proposal_id)
            return task_value(row, proposal) if proposal else None

    def save(self, owner_id: OwnerId, item: ActionItem, *, expected_revision: int | None) -> None:
        if owner_id != item.owner_id:
            raise RepositoryConflict("action ownership mismatch")
        proposal = PostgreSQLWorkspaceReads(self.engine).proposal(owner_id, item.proposal.id)
        if proposal != item.proposal:
            raise RepositoryConflict("immutable proposal mismatch")
        with self.transaction() as s:
            lock(s, f"task:{owner_id}:{item.id}")
            row = s.get(ActionItemRow, item.id, with_for_update=True)
            if expected_revision is None:
                if row is not None:
                    if row.owner_id != owner_id or task_value(row, proposal) != item:
                        raise RepositoryConflict("task identity conflict")
                    return
                if item.revision != 0 or item.status != ActionStatus.PROPOSED:
                    raise RepositoryConflict("initial task must be proposed revision zero")
                row = ActionItemRow(
                    id=item.id,
                    owner_id=owner_id,
                    proposal_id=proposal.id,
                    analysis_id=proposal.origin.analysis_id,
                    result_id=proposal.origin.result_id,
                )
                s.add(row)
            elif (
                row is None
                or row.owner_id != owner_id
                or row.proposal_id != proposal.id
                or row.revision != expected_revision
                or item.revision != expected_revision + 1
            ):
                raise RepositoryConflict("task revision changed; reload")
            row.title, row.description, row.status, row.revision = (
                item.title,
                item.description,
                item.status.value,
                item.revision,
            )
            row.deadline_raw = item.deadline.raw_text
            row.deadline_normalized = (
                item.deadline.normalized.isoformat() if item.deadline.normalized else None
            )
