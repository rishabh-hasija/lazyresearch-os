"""Scoped mission operations and atomic publication under PostgreSQL topic locks."""

import json
import re
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Literal, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lazyresearch.application.analysis import normalize_deadline
from lazyresearch.application.mission_comparison import compare_results
from lazyresearch.application.mission_models import (
    MissionError,
    MissionEvidence,
    MissionScope,
    SynthesisOutput,
    validate_brief,
)
from lazyresearch.domain.actions import ActionOrigin, ActionOriginType, ActionProposal, Deadline
from lazyresearch.domain.identity import MissionId, OwnerId, ProposalId, ResultId, TopicId
from lazyresearch.domain.processing import ProcessingIdentity
from lazyresearch.domain.research import (
    MissionStatus,
    ResearchMission,
    ResearchResult,
    ResearchTopic,
    ResultCoverage,
    plan_publication,
)
from lazyresearch.infrastructure.persistence.mission_models import (
    MissionEvidenceRow,
    MissionRow,
    MissionStageRow,
    ResearchProposalRow,
    ResultRow,
    TopicRow,
)
from lazyresearch.infrastructure.persistence.models import (
    BatchRow,
    CaptureRow,
    ContentRow,
    EntryRow,
    ExtractionRow,
)
from lazyresearch.infrastructure.persistence.repositories import DatabaseAdapter
from lazyresearch.infrastructure.persistence.retrieval_models import (
    ChunkRow,
    CollectionRow,
    RetrievalStateRow,
)


def dump(value: object) -> dict[str, object]:
    return cast(dict[str, object], json.loads(json.dumps(value, default=str)))


def mission_value(row: MissionRow) -> ResearchMission:
    return ResearchMission(
        id=MissionId(row.id),
        owner_id=OwnerId(row.owner_id),
        topic_id=TopicId(row.topic_id),
        question=row.question,
        run_sequence=row.run_sequence,
        baseline_result_id=ResultId(row.baseline_result_id) if row.baseline_result_id else None,
        status=MissionStatus(row.status),
        stage=row.stage,
    )


def processing_value(payload: dict[str, object]) -> ProcessingIdentity:
    return ProcessingIdentity(**cast(dict[str, str], payload))


class PostgreSQLMissionStore(DatabaseAdapter):
    def source_chunks(self, owner: UUID, content: UUID, version: str) -> tuple[UUID, ...]:
        with self.transaction() as s:
            state = s.get(RetrievalStateRow, (owner, content))
            if state is None or state.visibility != "ACTIVE":
                return ()
            return tuple(
                s.scalars(
                    select(ChunkRow.id)
                    .where(
                        ChunkRow.owner_id == owner,
                        ChunkRow.content_id == content,
                        ChunkRow.extraction_id == state.extraction_id,
                        ChunkRow.chunker_version == version,
                    )
                    .order_by(ChunkRow.ordinal)
                    .limit(2)
                )
            )

    @staticmethod
    def _row(s: Session, owner: UUID, mission: UUID) -> MissionRow:
        row = s.scalar(
            select(MissionRow)
            .where(MissionRow.id == mission, MissionRow.owner_id == owner)
            .with_for_update()
        )
        if row is None:
            raise MissionError("NOT_FOUND")
        return row

    @staticmethod
    def _active(row: MissionRow) -> None:
        if row.status != "RUNNING":
            raise MissionError("MISSION_NOT_RUNNING")
        scope = MissionScope.model_validate_json(json.dumps(row.inputs))
        if row.started_at and datetime.now(UTC) >= row.started_at + timedelta(
            seconds=scope.deadline_seconds
        ):
            raise MissionError("DEADLINE_EXCEEDED")

    def create_topic(
        self, owner: UUID, title: str, description: str | None = None
    ) -> ResearchTopic:
        topic = ResearchTopic(id=TopicId(uuid4()), owner_id=OwnerId(owner), title=title)
        with self.transaction() as s:
            s.add(TopicRow(id=topic.id, owner_id=owner, title=title, description=description))
        return topic

    def get_topic(self, owner_id: OwnerId, topic_id: TopicId) -> ResearchTopic | None:
        with self.transaction() as s:
            row = s.scalar(
                select(TopicRow).where(TopicRow.id == topic_id, TopicRow.owner_id == owner_id)
            )
            return (
                ResearchTopic(
                    id=TopicId(row.id),
                    owner_id=OwnerId(row.owner_id),
                    title=row.title,
                    current_result_id=ResultId(row.current_result_id)
                    if row.current_result_id
                    else None,
                )
                if row
                else None
            )

    def create_mission(
        self, owner: UUID, topic: UUID, question: str, scope: MissionScope
    ) -> ResearchMission:
        if not question.strip() or len(question) > 500 or len(question.encode()) > 2000:
            raise ValueError("question must be bounded and nonempty")
        with self.transaction() as s:
            row = s.scalar(
                select(TopicRow)
                .where(TopicRow.id == topic, TopicRow.owner_id == owner)
                .with_for_update()
            )
            if row is None:
                raise MissionError("NOT_FOUND")
            if scope.collection_ids:
                count = s.scalar(
                    select(func.count())
                    .select_from(CollectionRow)
                    .where(
                        CollectionRow.owner_id == owner, CollectionRow.id.in_(scope.collection_ids)
                    )
                )
                if count != len(set(scope.collection_ids)):
                    raise MissionError("INVALID_SCOPE")
            m = MissionRow(
                id=uuid4(),
                owner_id=owner,
                topic_id=topic,
                question=question,
                run_sequence=row.next_run,
                baseline_result_id=row.current_result_id,
                inputs=scope.model_dump(mode="json"),
                status="QUEUED",
                stage="mission_created",
            )
            row.next_run += 1
            s.add(m)
            s.flush()
            return mission_value(m)

    def get_mission(self, owner_id: OwnerId, mission_id: MissionId) -> ResearchMission | None:
        with self.transaction() as s:
            row = s.scalar(
                select(MissionRow).where(
                    MissionRow.id == mission_id, MissionRow.owner_id == owner_id
                )
            )
            return mission_value(row) if row else None

    def context(self, owner: UUID, mission: UUID) -> dict[str, object]:
        with self.transaction() as s:
            row = self._row(s, owner, mission)
            return {
                "question": row.question,
                "run_sequence": row.run_sequence,
                "status": row.status,
                "stage": row.stage,
                "inputs": row.inputs,
            }

    def scope(self, owner: UUID, mission: UUID) -> MissionScope:
        return MissionScope.model_validate_json(json.dumps(self.context(owner, mission)["inputs"]))

    def start(self, owner: UUID, mission: UUID) -> None:
        with self.transaction() as s:
            row = self._row(s, owner, mission)
            if row.status == "QUEUED":
                row.status, row.started_at = "RUNNING", datetime.now(UTC)
            self._active(row)

    def check(self, owner: UUID, mission: UUID) -> None:
        with self.transaction() as s:
            self._active(self._row(s, owner, mission))

    def terminal(self, owner: UUID, mission: UUID, status: str, reason: str) -> None:
        if status not in {"FAILED", "CANCELLED"}:
            raise ValueError("invalid terminal state")
        with self.transaction() as s:
            row = self._row(s, owner, mission)
            if row.status in {"QUEUED", "RUNNING"}:
                if row.status == "QUEUED" and status == "FAILED":
                    row.status = "RUNNING"
                    s.flush()
                mission_value(row).transition(MissionStatus(status))
                row.status, row.failure, row.completed_at = status, reason, datetime.now(UTC)

    def stage(self, owner: UUID, mission: UUID, name: str) -> dict[str, object] | None:
        with self.transaction() as s:
            row = s.scalar(
                select(MissionStageRow).where(
                    MissionStageRow.mission_id == mission,
                    MissionStageRow.owner_id == owner,
                    MissionStageRow.name == name,
                )
            )
            return row.payload if row else None

    def save_stage(
        self, owner: UUID, mission: UUID, name: str, payload: dict[str, object]
    ) -> dict[str, object]:
        with self.transaction() as s:
            row = self._row(s, owner, mission)
            self._active(row)
            existing = s.get(MissionStageRow, (mission, name))
            if existing:
                return existing.payload
            s.add(MissionStageRow(mission_id=mission, owner_id=owner, name=name, payload=payload))
            row.stage = name.split(":")[0]
            return payload

    def candidates(
        self, owner: UUID, mission: UUID, chunk_ids: tuple[UUID, ...], origin: str, method: str
    ) -> tuple[MissionEvidence, ...]:
        with self.transaction() as s:
            self._active(self._row(s, owner, mission))
            values = []
            for rank, key in enumerate(dict.fromkeys(chunk_ids), 1):
                chunk = s.scalar(
                    select(ChunkRow).where(ChunkRow.id == key, ChunkRow.owner_id == owner)
                )
                if chunk is None:
                    raise MissionError("INVALID_CITATION")
                content = s.get(ContentRow, chunk.content_id)
                assert content is not None
                capture = None
                if origin == "PUBLIC":
                    capture = s.scalar(
                        select(CaptureRow)
                        .join(EntryRow, CaptureRow.entry_id == EntryRow.id)
                        .join(BatchRow, EntryRow.batch_id == BatchRow.id)
                        .where(
                            CaptureRow.owner_id == owner,
                            CaptureRow.content_id == chunk.content_id,
                            BatchRow.request_key.like(f"mission:{mission}:source:%"),
                        )
                        .order_by(CaptureRow.captured_at.desc())
                        .limit(1)
                    )
                values.append(
                    MissionEvidence(
                        id=uuid5(NAMESPACE_URL, f"{mission}:{key}"),
                        owner_id=owner,
                        mission_id=mission,
                        content_id=chunk.content_id,
                        extraction_id=chunk.extraction_id,
                        chunk_id=key,
                        start=chunk.start,
                        end=chunk.end,
                        page=chunk.page,
                        quote=chunk.text,
                        text_hash=chunk.text_hash,
                        title=content.original_title,
                        url=content.original_url,
                        origin=cast(Literal["PERSONAL", "PUBLIC"], origin),
                        method=method,
                        rank=rank,
                        score=1.0 / rank,
                        retrieved_at=datetime.now(UTC),
                        fetched_at=capture.captured_at if capture else content.captured_at,
                        published_at=content.published_at,
                        capture_id=capture.id if capture else None,
                        fetched_url=capture.final_url if capture else content.canonical_url,
                    )
                )
            return tuple(values)

    @staticmethod
    def _validate(s: Session, e: MissionEvidence) -> None:
        chunk = s.scalar(
            select(ChunkRow).where(ChunkRow.id == e.chunk_id, ChunkRow.owner_id == e.owner_id)
        )
        extraction = s.scalar(
            select(ExtractionRow).where(
                ExtractionRow.id == e.extraction_id,
                ExtractionRow.owner_id == e.owner_id,
                ExtractionRow.content_id == e.content_id,
            )
        )
        state = s.get(RetrievalStateRow, (e.owner_id, e.content_id))
        if (
            chunk is None
            or extraction is None
            or state is None
            or state.visibility != "ACTIVE"
            or chunk.extraction_id != e.extraction_id
            or chunk.content_id != e.content_id
            or (chunk.start, chunk.end, chunk.page, chunk.text, chunk.text_hash)
            != (e.start, e.end, e.page, e.quote, e.text_hash)
            or extraction.text[e.start : e.end] != e.quote
        ):
            raise MissionError("INVALID_CITATION")
        e.locator()

    def freeze(
        self, owner: UUID, mission: UUID, evidence: tuple[MissionEvidence, ...]
    ) -> tuple[MissionEvidence, ...]:
        with self.transaction() as s:
            row = self._row(s, owner, mission)
            self._active(row)
            if not row.frozen:
                if not evidence:
                    raise MissionError("NO_EVIDENCE")
                for e in evidence:
                    if e.owner_id != owner or e.mission_id != mission:
                        raise MissionError("INVALID_CITATION")
                    self._validate(s, e)
                    state = s.get(RetrievalStateRow, (owner, e.content_id))
                    if state is None or state.extraction_id != e.extraction_id:
                        raise MissionError("STALE_EXTRACTION")
                    s.add(
                        MissionEvidenceRow(
                            id=e.id,
                            owner_id=owner,
                            mission_id=mission,
                            content_id=e.content_id,
                            extraction_id=e.extraction_id,
                            chunk_id=e.chunk_id,
                            payload=e.model_dump(mode="json"),
                        )
                    )
                s.flush()
                row.frozen = True
        return self.evidence(owner, mission)

    def evidence(self, owner: UUID, mission: UUID) -> tuple[MissionEvidence, ...]:
        with self.transaction() as s:
            rows = s.scalars(
                select(MissionEvidenceRow)
                .where(
                    MissionEvidenceRow.owner_id == owner, MissionEvidenceRow.mission_id == mission
                )
                .order_by(MissionEvidenceRow.id)
            ).all()
            return tuple(MissionEvidence.model_validate_json(json.dumps(e.payload)) for e in rows)

    def validate_evidence(self, owner: UUID, mission: UUID) -> None:
        evidence = self.evidence(owner, mission)
        if not evidence:
            raise MissionError("NO_EVIDENCE")
        with self.transaction() as s:
            for e in evidence:
                self._validate(s, e)

    def baseline(self, owner: UUID, mission: UUID) -> dict[str, object] | None:
        with self.transaction() as s:
            m = self._row(s, owner, mission)
            row = s.get(ResultRow, m.baseline_result_id) if m.baseline_result_id else None
            return row.payload if row else None

    def get_result(self, owner_id: OwnerId, result_id: ResultId) -> ResearchResult | None:
        with self.transaction() as s:
            row = s.scalar(
                select(ResultRow).where(ResultRow.id == result_id, ResultRow.owner_id == owner_id)
            )
            return self._result(row) if row else None

    @staticmethod
    def _result(row: ResultRow) -> ResearchResult:
        p = row.payload
        evidence = tuple(
            MissionEvidence.model_validate_json(json.dumps(e)).locator()
            for e in cast(list[object], p["evidence"])
        )
        brief = cast(dict[str, object], p["brief"])
        return ResearchResult(
            id=ResultId(row.id),
            owner_id=OwnerId(row.owner_id),
            topic_id=TopicId(row.topic_id),
            mission_id=MissionId(row.mission_id),
            run_sequence=row.run_sequence,
            version=row.version,
            published_at=row.created_at,
            answer=str(cast(dict[str, object], brief["answer"])["text"]),
            processing=processing_value(cast(dict[str, object], p["processing"])),
            evidence=evidence,
            baseline_result_id=ResultId(row.baseline_result_id) if row.baseline_result_id else None,
            coverage=ResultCoverage(row.coverage),
            limitations=tuple(cast(list[str], p["limitations"])),
        )

    def versions(self, owner: UUID, topic: UUID) -> tuple[ResearchResult, ...]:
        with self.transaction() as s:
            return tuple(
                self._result(row)
                for row in s.scalars(
                    select(ResultRow)
                    .where(ResultRow.owner_id == owner, ResultRow.topic_id == topic)
                    .order_by(ResultRow.version)
                )
            )

    def pending_dispatches(self, limit: int = 100) -> tuple[tuple[UUID, UUID, int], ...]:
        with self.transaction() as s:
            rows = s.scalars(
                select(MissionRow)
                .where(
                    MissionRow.dispatched.is_(False), MissionRow.status.in_(("QUEUED", "RUNNING"))
                )
                .order_by(MissionRow.created_at)
                .limit(min(limit, 100))
            )
            return tuple(
                (
                    r.owner_id,
                    r.id,
                    MissionScope.model_validate_json(json.dumps(r.inputs)).deadline_seconds,
                )
                for r in rows
            )

    def mark_dispatched(self, owner: UUID, mission: UUID) -> None:
        with self.transaction() as s:
            self._row(s, owner, mission).dispatched = True

    def active_dispatches(self) -> tuple[tuple[UUID, UUID], ...]:
        with self.transaction() as s:
            return tuple(
                (r.owner_id, r.id)
                for r in s.scalars(
                    select(MissionRow)
                    .where(
                        MissionRow.dispatched.is_(True),
                        MissionRow.status.in_(("QUEUED", "RUNNING")),
                    )
                    .order_by(MissionRow.created_at)
                    .limit(100)
                )
            )

    def reset_dispatch(self, owner: UUID, mission: UUID) -> None:
        with self.transaction() as s:
            row = self._row(s, owner, mission)
            if row.status in {"QUEUED", "RUNNING"}:
                row.dispatched = False

    def publish(self, owner: UUID, mission: UUID) -> UUID:
        # Always acquire topic before mission: every publisher uses the same lock order.
        with self.transaction() as s:
            topic_id = s.scalar(
                select(MissionRow.topic_id).where(
                    MissionRow.id == mission, MissionRow.owner_id == owner
                )
            )
            topic = s.scalar(
                select(TopicRow)
                .where(TopicRow.id == topic_id, TopicRow.owner_id == owner)
                .with_for_update()
            )
            if topic is None:
                raise MissionError("NOT_FOUND")
            m = self._row(s, owner, mission)
            existing = s.scalar(select(ResultRow).where(ResultRow.mission_id == mission))
            if existing:
                return existing.id
            self._active(m)
            if not m.frozen:
                raise MissionError("EVIDENCE_NOT_FROZEN")
            stage = s.get(MissionStageRow, (mission, "synthesize"))
            if stage is None:
                raise MissionError("SYNTHESIS_MISSING")
            output = SynthesisOutput.model_validate_json(json.dumps(stage.payload))
            evidence = tuple(
                MissionEvidence.model_validate_json(json.dumps(e.payload))
                for e in s.scalars(
                    select(MissionEvidenceRow)
                    .where(
                        MissionEvidenceRow.mission_id == mission,
                        MissionEvidenceRow.owner_id == owner,
                    )
                    .order_by(MissionEvidenceRow.id)
                )
            )
            for e in evidence:
                self._validate(s, e)
            validate_brief(output.brief, evidence)
            limitations = list(output.brief.coverage_limitations)
            for stage_row in s.scalars(
                select(MissionStageRow).where(MissionStageRow.mission_id == mission)
            ):
                limitations.extend(cast(list[str], stage_row.payload.get("limitations", [])))
            limitations = list(dict.fromkeys(limitations))
            processing = ProcessingIdentity(
                provider=output.provider,
                model=output.model,
                model_revision=output.model_revision,
                provider_revision=output.runtime,
                prompt_version="research-v1",
                prompt_hash=output.prompt_hash,
                schema_version="research-v1",
                pipeline_version="mission-v1",
                input_hash=sha256(
                    json.dumps(
                        [(str(e.chunk_id), e.text_hash) for e in evidence], sort_keys=True
                    ).encode()
                ).hexdigest(),
            )
            result_id = uuid5(NAMESPACE_URL, f"research-result:{mission}")
            result = ResearchResult(
                id=ResultId(result_id),
                owner_id=OwnerId(owner),
                topic_id=TopicId(topic.id),
                mission_id=MissionId(mission),
                run_sequence=m.run_sequence,
                version=topic.next_version,
                published_at=datetime.now(UTC),
                answer=output.brief.answer.text,
                processing=processing,
                evidence=tuple(e.locator() for e in evidence),
                baseline_result_id=ResultId(m.baseline_result_id) if m.baseline_result_id else None,
                coverage=ResultCoverage.PARTIAL if limitations else ResultCoverage.COMPLETE,
                limitations=tuple(limitations),
            )
            current = s.get(ResultRow, topic.current_result_id) if topic.current_result_id else None
            decision = plan_publication(
                mission_value(m), result, current_brief=self._result(current) if current else None
            )
            baseline = s.get(ResultRow, m.baseline_result_id) if m.baseline_result_id else None
            processing_data = dump(asdict(processing))
            conflicts = s.get(MissionStageRow, (mission, "detect_conflicts"))
            payload = {
                "brief": output.brief.model_dump(mode="json"),
                "evidence": [e.model_dump(mode="json") for e in evidence],
                "processing": processing_data,
                "limitations": limitations,
                "contradictions": conflicts.payload if conflicts else {},
                "changes": compare_results(
                    baseline.payload if baseline else None, output.brief, evidence, processing_data
                ),
            }
            s.add(
                ResultRow(
                    id=result_id,
                    owner_id=owner,
                    topic_id=topic.id,
                    mission_id=mission,
                    version=result.version,
                    run_sequence=m.run_sequence,
                    baseline_result_id=m.baseline_result_id,
                    coverage=result.coverage.value,
                    created_at=result.published_at,
                    payload=payload,
                )
            )
            s.flush()
            registry = {e.id: e for e in evidence}
            for ordinal, action in enumerate(output.brief.action_candidates):
                sources = tuple(registry[key].locator() for key in action.evidence)
                deadline = (
                    normalize_deadline(action.deadline_raw)
                    if action.uncertainty == "low"
                    else Deadline(raw_text=action.deadline_raw)
                )
                explicit_dates = {
                    d
                    for source in sources
                    for d in re.findall(r"\b\d{4}-\d{2}-\d{2}\b", source.quote)
                }
                if len(explicit_dates) > 1:
                    deadline = Deadline(raw_text=action.deadline_raw)
                proposal = ActionProposal(
                    id=ProposalId(uuid5(result_id, str(ordinal))),
                    owner_id=OwnerId(owner),
                    title=action.title,
                    description=action.description,
                    origin=ActionOrigin(
                        kind=ActionOriginType.RESEARCH_RESULT, result_id=ResultId(result_id)
                    ),
                    candidate_ordinal=ordinal,
                    processing=processing,
                    evidence=sources,
                    deadline=deadline,
                    uncertainty=action.uncertainty,
                )
                s.add(
                    ResearchProposalRow(
                        id=proposal.id,
                        owner_id=owner,
                        result_id=result_id,
                        ordinal=ordinal,
                        payload=dump(asdict(proposal)),
                    )
                )
            topic.next_version += 1
            topic.current_result_id = decision.current_brief.id
            topic.updated_at = datetime.now(UTC)
            m.status, m.stage, m.completed_at = (
                decision.mission.status.value,
                "complete",
                datetime.now(UTC),
            )
            return result_id
