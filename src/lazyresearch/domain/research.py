"""Research lifecycle and pure publication decisions; no transaction/version allocator."""

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from typing import Self

from lazyresearch.domain._validation import require_count, require_id, require_text, utc_instant
from lazyresearch.domain.content import SourceEvidence
from lazyresearch.domain.errors import (
    DomainError,
    InvalidResearchPublication,
    InvalidStateTransition,
    MissingProvenance,
)
from lazyresearch.domain.identity import MissionId, OwnerId, ResultId, TopicId
from lazyresearch.domain.processing import ProcessingIdentity


class MissionStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ResultCoverage(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"


@dataclass(frozen=True, slots=True, kw_only=True)
class ResearchTopic:
    """Explicit identity/association, never deduced from question similarity."""

    id: TopicId
    owner_id: OwnerId
    title: str
    current_result_id: ResultId | None = None

    def __post_init__(self) -> None:
        require_id(self.id, "id")
        require_id(self.owner_id, "owner_id")
        require_text(self.title, "title")
        if self.current_result_id is not None:
            require_id(self.current_result_id, "current_result_id")


@dataclass(frozen=True, slots=True, kw_only=True)
class ResearchMission:
    """Frozen inputs and immutable snapshots of operational state.

    Completion state alone does not publish anything: the later transaction must
    commit the publication decision and mission completion together.
    """

    id: MissionId
    owner_id: OwnerId
    topic_id: TopicId
    question: str
    run_sequence: int
    baseline_result_id: ResultId | None = None
    status: MissionStatus = MissionStatus.QUEUED
    stage: str | None = None

    def __post_init__(self) -> None:
        require_id(self.id, "id")
        require_id(self.owner_id, "owner_id")
        require_id(self.topic_id, "topic_id")
        require_text(self.question, "question")
        require_count(self.run_sequence, "run_sequence")
        if self.baseline_result_id is not None:
            require_id(self.baseline_result_id, "baseline_result_id")
        if not isinstance(self.status, MissionStatus):
            raise DomainError("status must be MissionStatus")
        if self.stage is not None:
            require_text(self.stage, "stage")

    def transition(self, target: MissionStatus, *, stage: str | None = None) -> Self:
        allowed = {
            MissionStatus.QUEUED: {MissionStatus.RUNNING, MissionStatus.CANCELLED},
            MissionStatus.RUNNING: {
                MissionStatus.COMPLETED,
                MissionStatus.PARTIAL,
                MissionStatus.FAILED,
                MissionStatus.CANCELLED,
            },
        }
        if not isinstance(target, MissionStatus) or target not in allowed.get(self.status, set()):
            raise InvalidStateTransition(f"mission cannot transition {self.status} -> {target}")
        return replace(self, status=target, stage=stage)


@dataclass(frozen=True, slots=True, kw_only=True)
class ResearchResult:
    """Immutable publication value. Version is supplied, never allocated here.

    Construction validates the value; only a repository transaction can establish
    that it has actually been published exactly once.
    """

    id: ResultId
    owner_id: OwnerId
    topic_id: TopicId
    mission_id: MissionId
    run_sequence: int
    version: int
    published_at: datetime
    answer: str = field(repr=False)
    processing: ProcessingIdentity
    evidence: tuple[SourceEvidence, ...] = field(repr=False)
    baseline_result_id: ResultId | None = None
    coverage: ResultCoverage = ResultCoverage.COMPLETE
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("id", "owner_id", "topic_id", "mission_id"):
            require_id(getattr(self, name), name)
        require_count(self.run_sequence, "run_sequence")
        require_count(self.version, "version")
        require_text(self.answer, "answer")
        if not isinstance(self.processing, ProcessingIdentity):
            raise DomainError("result requires processing identity")
        if not isinstance(self.coverage, ResultCoverage):
            raise DomainError("coverage must be ResultCoverage")
        if self.baseline_result_id is not None:
            require_id(self.baseline_result_id, "baseline_result_id")
            if self.baseline_result_id == self.id:
                raise InvalidResearchPublication("a result cannot be its own baseline")
        object.__setattr__(self, "published_at", utc_instant(self.published_at, "published_at"))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "limitations", tuple(self.limitations))
        if not self.evidence:
            raise MissingProvenance("a published result requires source evidence")
        for source in self.evidence:
            if not isinstance(source, SourceEvidence) or source.owner_id != self.owner_id:
                raise MissingProvenance("result evidence must belong to the result owner")
        for limitation in self.limitations:
            require_text(limitation, "limitation")
        if self.coverage is ResultCoverage.PARTIAL and not self.limitations:
            raise InvalidResearchPublication("a partial result must explain its limitations")


@dataclass(frozen=True, slots=True, kw_only=True)
class PublicationDecision:
    """Policy output; not a receipt proving a transaction took place."""

    result: ResearchResult
    mission: ResearchMission
    current_brief: ResearchResult
    is_new: bool


def plan_publication(
    mission: ResearchMission,
    candidate: ResearchResult,
    *,
    current_brief: ResearchResult | None = None,
    existing_result: ResearchResult | None = None,
) -> PublicationDecision:
    """Validate supplied history and choose Current Brief by mission run sequence.

    Callers must supply the same mission's existing result, even if historical.
    Exact repeat inputs reuse it; conflicting publication inputs are rejected.
    The future repository must read these records, allocate version, enforce
    unique mission/topic sequence constraints, and commit under a transaction.
    This function provides none of those storage/concurrency guarantees.
    """
    if mission.status in {MissionStatus.FAILED, MissionStatus.CANCELLED, MissionStatus.QUEUED}:
        raise InvalidResearchPublication("only a running mission can first publish")
    if (
        candidate.owner_id != mission.owner_id
        or candidate.topic_id != mission.topic_id
        or candidate.mission_id != mission.id
        or candidate.run_sequence != mission.run_sequence
        or candidate.baseline_result_id != mission.baseline_result_id
    ):
        raise InvalidResearchPublication("result does not match frozen mission inputs")
    if current_brief is not None:
        if current_brief.owner_id != mission.owner_id or current_brief.topic_id != mission.topic_id:
            raise InvalidResearchPublication(
                "Current Brief must belong to the same owner and topic"
            )
        if current_brief.mission_id == mission.id:
            if existing_result is not None and existing_result != current_brief:
                raise InvalidResearchPublication("stored publication history disagrees")
            existing_result = current_brief
        elif current_brief.run_sequence == mission.run_sequence:
            raise InvalidResearchPublication("two different missions cannot share a run sequence")
        elif current_brief.id == candidate.id:
            raise InvalidResearchPublication("a result ID cannot be reused by another mission")

    completed_status = (
        MissionStatus.COMPLETED
        if candidate.coverage is ResultCoverage.COMPLETE
        else MissionStatus.PARTIAL
    )
    if existing_result is not None:
        if existing_result != candidate:
            raise InvalidResearchPublication("a mission cannot overwrite its published result")
        if mission.status not in {MissionStatus.RUNNING, completed_status}:
            raise InvalidResearchPublication("mission status disagrees with published coverage")
        is_new = False
    else:
        if mission.status is not MissionStatus.RUNNING:
            raise InvalidResearchPublication("completed mission requires its stored publication")
        if current_brief is not None and candidate.version <= current_brief.version:
            raise InvalidResearchPublication("new publication version must advance")
        is_new = True

    completed = (
        mission.transition(completed_status, stage="complete")
        if mission.status is MissionStatus.RUNNING
        else mission
    )
    selected = (
        candidate
        if current_brief is None or candidate.run_sequence > current_brief.run_sequence
        else current_brief
    )
    return PublicationDecision(
        result=existing_result if existing_result is not None else candidate,
        mission=completed,
        current_brief=selected,
        is_new=is_new,
    )
