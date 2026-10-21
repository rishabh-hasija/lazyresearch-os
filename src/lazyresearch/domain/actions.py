"""Immutable action proposals and separately editable task-state snapshots."""

from dataclasses import dataclass, field, replace
from datetime import date, datetime
from enum import StrEnum
from typing import Self

from lazyresearch.domain._validation import require_count, require_id, require_text, utc_instant
from lazyresearch.domain.content import SourceEvidence
from lazyresearch.domain.errors import (
    DomainError,
    InvalidStateTransition,
    MissingProvenance,
    RevisionConflict,
)
from lazyresearch.domain.identity import ActionId, AnalysisId, OwnerId, ProposalId, ResultId
from lazyresearch.domain.processing import ProcessingIdentity


@dataclass(frozen=True, slots=True, kw_only=True)
class Deadline:
    """None means unresolved, date means date-only, datetime means a known instant."""

    raw_text: str | None = None
    normalized: date | datetime | None = None

    def __post_init__(self) -> None:
        if self.raw_text is not None:
            require_text(self.raw_text, "raw_text")
        if isinstance(self.normalized, datetime):
            object.__setattr__(self, "normalized", utc_instant(self.normalized, "deadline"))
        elif self.normalized is not None and not isinstance(self.normalized, date):
            raise DomainError("deadline must be a date, aware datetime, or unresolved")


class ActionOriginType(StrEnum):
    SOURCE_ANALYSIS = "SOURCE_ANALYSIS"
    RESEARCH_RESULT = "RESEARCH_RESULT"


@dataclass(frozen=True, slots=True, kw_only=True)
class ActionOrigin:
    kind: ActionOriginType
    analysis_id: AnalysisId | None = None
    result_id: ResultId | None = None

    def __post_init__(self) -> None:
        if self.kind is ActionOriginType.SOURCE_ANALYSIS:
            if self.analysis_id is None or self.result_id is not None:
                raise MissingProvenance("analysis origin requires only analysis_id")
            require_id(self.analysis_id, "analysis_id")
        elif self.kind is ActionOriginType.RESEARCH_RESULT:
            if self.result_id is None or self.analysis_id is not None:
                raise MissingProvenance("result origin requires only result_id")
            require_id(self.result_id, "result_id")
        else:
            raise MissingProvenance("unknown action origin")


@dataclass(frozen=True, slots=True, kw_only=True)
class ActionProposal:
    id: ProposalId
    owner_id: OwnerId
    title: str
    description: str
    origin: ActionOrigin
    candidate_ordinal: int
    processing: ProcessingIdentity
    evidence: tuple[SourceEvidence, ...] = field(repr=False)
    deadline: Deadline = Deadline()
    uncertainty: str = "unknown"
    kind: str = "task"

    def __post_init__(self) -> None:
        require_id(self.id, "id")
        require_id(self.owner_id, "owner_id")
        require_text(self.title, "title")
        require_text(self.description, "description")
        require_count(self.candidate_ordinal, "candidate_ordinal", minimum=0)
        if self.uncertainty not in {"unknown", "low", "medium", "high"}:
            raise DomainError("unknown candidate uncertainty")
        if self.kind not in {
            "task",
            "deadline",
            "follow_up",
            "form",
            "application",
            "renewal",
            "decision",
            "purchase",
            "event",
        }:
            raise DomainError("unknown candidate kind")
        if not isinstance(self.processing, ProcessingIdentity):
            raise DomainError("proposal requires processing identity")
        if not isinstance(self.origin, ActionOrigin):
            raise MissingProvenance("proposal requires a generated artifact origin")
        if not isinstance(self.deadline, Deadline):
            raise DomainError("proposal requires a Deadline value")
        object.__setattr__(self, "evidence", tuple(self.evidence))
        if not self.evidence:
            raise MissingProvenance("every action proposal requires original source evidence")
        for source in self.evidence:
            if not isinstance(source, SourceEvidence) or source.owner_id != self.owner_id:
                raise MissingProvenance("action evidence must belong to the proposal owner")


class ActionStatus(StrEnum):
    PROPOSED = "PROPOSED"
    ACCEPTED = "ACCEPTED"
    COMPLETED = "COMPLETED"
    DISMISSED = "DISMISSED"


@dataclass(frozen=True, slots=True, kw_only=True)
class ActionItem:
    id: ActionId
    proposal: ActionProposal
    title: str
    description: str
    deadline: Deadline
    status: ActionStatus = ActionStatus.PROPOSED
    revision: int = 0

    def __post_init__(self) -> None:
        require_id(self.id, "id")
        if not isinstance(self.proposal, ActionProposal):
            raise MissingProvenance("action must retain its original proposal")
        require_text(self.title, "title")
        require_text(self.description, "description")
        if not isinstance(self.deadline, Deadline) or not isinstance(self.status, ActionStatus):
            raise DomainError("action requires typed deadline and status")
        require_count(self.revision, "revision", minimum=0)

    @property
    def owner_id(self) -> OwnerId:
        return self.proposal.owner_id

    @classmethod
    def from_proposal(cls, id: ActionId, proposal: ActionProposal) -> Self:
        return cls(
            id=id,
            proposal=proposal,
            title=proposal.title,
            description=proposal.description,
            deadline=proposal.deadline,
        )

    def _check_revision(self, expected_revision: int) -> None:
        require_count(expected_revision, "expected_revision", minimum=0)
        if expected_revision != self.revision:
            raise RevisionConflict("task revision changed; reload before editing")

    def transition(self, target: ActionStatus, *, expected_revision: int) -> Self:
        self._check_revision(expected_revision)
        allowed = {
            ActionStatus.PROPOSED: {ActionStatus.ACCEPTED, ActionStatus.DISMISSED},
            ActionStatus.ACCEPTED: {ActionStatus.COMPLETED, ActionStatus.DISMISSED},
            ActionStatus.COMPLETED: {ActionStatus.ACCEPTED},
            ActionStatus.DISMISSED: {ActionStatus.ACCEPTED},
        }
        if not isinstance(target, ActionStatus) or target not in allowed[self.status]:
            raise InvalidStateTransition(f"action cannot transition {self.status} -> {target}")
        return replace(self, status=target, revision=self.revision + 1)

    def edit(
        self,
        *,
        title: str,
        description: str,
        deadline: Deadline,
        expected_revision: int,
    ) -> Self:
        """Full user-state replacement allows clearing a deadline without a sentinel."""
        self._check_revision(expected_revision)
        return replace(
            self,
            title=title,
            description=description,
            deadline=deadline,
            revision=self.revision + 1,
        )
