"""Bounded immutable mission boundary values; no workflow/provider types."""

import re
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from lazyresearch.application.analysis_models import StrictSchema, Text
from lazyresearch.domain.content import SourceEvidence
from lazyresearch.domain.identity import ContentId, ExtractionId, OwnerId

Ids = Annotated[tuple[UUID, ...], Field(min_length=1, max_length=20)]


class MissionScope(StrictSchema):
    personal: bool = True
    public: bool = False
    collection_ids: Annotated[tuple[UUID, ...], Field(max_length=20)] = ()
    lexical: bool = True
    vector: bool = False
    max_queries: Annotated[int, Field(ge=0, le=3)] = 3
    max_sources: Annotated[int, Field(ge=0, le=10)] = 10
    fetch_concurrency: Annotated[int, Field(ge=1, le=5)] = 5
    deadline_seconds: Annotated[int, Field(ge=30, le=900)] = 900
    max_evidence: Annotated[int, Field(ge=1, le=20)] = 8
    max_evidence_chars: Annotated[int, Field(ge=1000, le=12000)] = 6000
    max_output_tokens: Annotated[int, Field(ge=256, le=3000)] = 2400
    freshness_days: Annotated[int, Field(ge=1, le=3650)] = 90
    require_current: bool = False

    @model_validator(mode="after")
    def valid_modes(self) -> "MissionScope":
        if not self.lexical and not self.vector:
            raise ValueError("at least one retrieval mode required")
        return self


class MissionEvidence(StrictSchema):
    id: UUID
    owner_id: UUID
    mission_id: UUID
    content_id: UUID
    extraction_id: UUID
    chunk_id: UUID
    start: int
    end: int
    page: int | None
    quote: str = Field(repr=False)
    text_hash: str
    title: str | None
    url: str | None
    origin: Literal["PERSONAL", "PUBLIC"]
    method: str
    rank: int
    score: float
    retrieved_at: datetime
    fetched_at: datetime
    published_at: datetime | None = None
    capture_id: UUID | None = None
    fetched_url: str | None = None

    def locator(self) -> SourceEvidence:
        return SourceEvidence(
            owner_id=OwnerId(self.owner_id),
            content_id=ContentId(self.content_id),
            extraction_id=ExtractionId(self.extraction_id),
            start=self.start,
            end=self.end,
            page=self.page,
            quote=self.quote,
        )


class SearchHit(StrictSchema):
    provider_id: str | None = None
    url: str
    title: str
    snippet: str = Field(default="", repr=False)
    rank: int
    published_at: datetime | None = None


class GapDecision(StrictSchema):
    reasons: tuple[str, ...]
    permitted: bool
    queries: tuple[str, ...]


class CitedClaim(StrictSchema):
    text: Text
    evidence: Ids
    uncertainty: Literal["low", "medium", "high"] = "medium"
    support: Literal["UNREVIEWED"] = "UNREVIEWED"


class MissionAction(StrictSchema):
    title: Annotated[str, Field(min_length=1, max_length=120)]
    description: Text
    evidence: Ids
    deadline_raw: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    uncertainty: Literal["low", "medium", "high"] = "medium"


class Contradiction(StrictSchema):
    evidence_a: UUID
    evidence_b: UUID
    kind: Literal["DATE", "PRICE", "QUANTITY", "VERSION", "FRESHNESS", "RECOMMENDATION"]
    description: Text
    uncertainty: Literal["high"] = "high"
    resolution: Literal["UNRESOLVED"] = "UNRESOLVED"


class ResearchBrief(StrictSchema):
    schema_version: Literal["research-v1"] = "research-v1"
    answer: CitedClaim
    summary: CitedClaim
    findings: Annotated[tuple[CitedClaim, ...], Field(min_length=1, max_length=12)]
    comparisons: Annotated[tuple[CitedClaim, ...], Field(max_length=8)] = ()
    recommendations: Annotated[tuple[CitedClaim, ...], Field(max_length=8)] = ()
    claims: Annotated[tuple[CitedClaim, ...], Field(max_length=12)] = ()
    action_candidates: Annotated[tuple[MissionAction, ...], Field(max_length=8)] = ()
    open_questions: Annotated[tuple[Text, ...], Field(max_length=10)] = ()
    missing_information: Annotated[tuple[Text, ...], Field(max_length=10)] = ()
    coverage_limitations: Annotated[tuple[Text, ...], Field(max_length=10)] = ()

    def cited(self) -> tuple[CitedClaim | MissionAction, ...]:
        return (
            self.answer,
            self.summary,
            *self.findings,
            *self.comparisons,
            *self.recommendations,
            *self.claims,
            *self.action_candidates,
        )


class SynthesisRequest(StrictSchema):
    question: str = Field(repr=False)
    scope: MissionScope
    evidence: tuple[MissionEvidence, ...] = Field(repr=False)
    contradictions: tuple[Contradiction, ...]
    baseline_summary: str | None = Field(default=None, repr=False)


class SynthesisOutput(StrictSchema):
    brief: ResearchBrief
    provider: str
    model: str
    model_revision: str | None
    runtime: str | None
    prompt_hash: str
    latency_seconds: float
    repaired: bool


class MissionError(Exception):
    """Sanitized permanent mission error."""


class TransientMissionError(MissionError):
    """Only this category permits provider/activity retries."""


def validate_brief(brief: ResearchBrief, evidence: tuple[MissionEvidence, ...]) -> None:
    registry = {e.id: e for e in evidence}
    if not registry:
        raise MissionError("NO_EVIDENCE")
    for claim in brief.cited():
        if any(key not in registry for key in claim.evidence):
            raise MissionError("INVALID_CITATION")
        text = (
            claim.text if isinstance(claim, CitedClaim) else claim.title + " " + claim.description
        )
        inline = re.findall(r"\b[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b", text)
        if any(UUID(key) not in claim.evidence for key in inline) or re.search(
            r"https?://|\[\d+\]", text
        ):
            raise MissionError("INVALID_CITATION")
    for text in (*brief.open_questions, *brief.missing_information, *brief.coverage_limitations):
        inline = re.findall(r"\b[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b", text)
        if any(UUID(key) not in registry for key in inline):
            raise MissionError("INVALID_CITATION")
    for action in brief.action_candidates:
        if action.deadline_raw and not any(
            action.deadline_raw in registry[key].quote for key in action.evidence
        ):
            raise MissionError("INVALID_DEADLINE")
