"""Immutable source analysis; citation validity is not factual entailment."""

from dataclasses import dataclass, field
from uuid import UUID

from lazyresearch.domain._validation import require_id, require_text
from lazyresearch.domain.actions import ActionProposal
from lazyresearch.domain.content import SourceEvidence
from lazyresearch.domain.errors import DomainError
from lazyresearch.domain.identity import AnalysisId, ContentId, OwnerId
from lazyresearch.domain.processing import ProcessingIdentity


@dataclass(frozen=True, slots=True, kw_only=True)
class CitedStatement:
    text: str
    uncertainty: str
    evidence: tuple[SourceEvidence, ...] = field(repr=False)
    support_review: str = "UNREVIEWED"

    def __post_init__(self) -> None:
        require_text(self.text, "text")
        object.__setattr__(self, "evidence", tuple(self.evidence))
        if not self.evidence or self.uncertainty not in {"low", "medium", "high"}:
            raise DomainError("statement requires evidence and uncertainty")
        if self.support_review != "UNREVIEWED":
            raise DomainError("machine citations do not prove support")


@dataclass(frozen=True, slots=True, kw_only=True)
class ContentAnalysis:
    id: AnalysisId
    owner_id: OwnerId
    content_id: ContentId
    extraction_id: UUID
    run_id: UUID
    version: str
    processing: ProcessingIdentity
    summaries: tuple[str, ...]
    topics: tuple[str, ...]
    entities: tuple[CitedStatement, ...]
    claims: tuple[CitedStatement, ...]
    actionability: str
    proposals: tuple[ActionProposal, ...]
    covered_ranges: tuple[tuple[int, int], ...]
    total_chars: int
    coverage: str

    def __post_init__(self) -> None:
        for name in ("id", "owner_id", "content_id", "extraction_id", "run_id"):
            require_id(getattr(self, name), name)
        require_text(self.version, "version")
        for name in ("summaries", "topics", "entities", "claims", "proposals", "covered_ranges"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        if not isinstance(self.processing, ProcessingIdentity):
            raise DomainError("analysis requires processing identity")
        if self.coverage not in {"COMPLETE", "PARTIAL"} or self.total_chars < 1:
            raise DomainError("invalid analysis coverage")
        if not self.summaries or not self.covered_ranges:
            raise DomainError("analysis requires summaries and explicit coverage")
        if self.actionability not in {
            "action_required",
            "no_action",
            "uncertain",
            "insufficient_information",
        }:
            raise DomainError("unknown actionability")
        for summary in self.summaries:
            require_text(summary, "summary")
        for topic in self.topics:
            require_text(topic, "topic")
        previous = 0
        for start, end in self.covered_ranges:
            if start != previous or end <= start or end > self.total_chars:
                raise DomainError("coverage must be ordered contiguous extraction spans")
            previous = end
        if (previous == self.total_chars) != (self.coverage == "COMPLETE"):
            raise DomainError("coverage label differs from processed spans")
        for statement in (*self.claims, *self.entities):
            if not isinstance(statement, CitedStatement):
                raise DomainError("analysis requires typed cited statements")
            for evidence in statement.evidence:
                if (evidence.owner_id, evidence.content_id, evidence.extraction_id) != (
                    self.owner_id,
                    self.content_id,
                    self.extraction_id,
                ):
                    raise DomainError("statement evidence scope differs from analysis")
        for index, proposal in enumerate(self.proposals):
            if (
                proposal.owner_id != self.owner_id
                or proposal.origin.analysis_id != self.id
                or proposal.candidate_ordinal != index
                or proposal.processing != self.processing
            ):
                raise DomainError("proposal origin or identity differs from analysis")
