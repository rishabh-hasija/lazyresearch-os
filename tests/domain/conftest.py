"""Deterministic synthetic values; no clocks, random IDs, I/O adapters, or providers."""

from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

import pytest

from lazyresearch.domain.actions import ActionOrigin, ActionOriginType, ActionProposal
from lazyresearch.domain.content import ContentItem, SourceEvidence, SourceType
from lazyresearch.domain.identity import (
    AnalysisId,
    ContentId,
    ExtractionId,
    MissionId,
    OwnerId,
    ProposalId,
    ResultId,
    TopicId,
)
from lazyresearch.domain.processing import ProcessingIdentity
from lazyresearch.domain.research import MissionStatus, ResearchMission, ResearchResult


@pytest.fixture
def instant() -> datetime:
    return datetime(2026, 10, 21, 10, tzinfo=UTC)


@pytest.fixture
def content(instant: datetime) -> ContentItem:
    raw = b"Reply by Friday."
    return ContentItem(
        id=ContentId(UUID(int=1)),
        owner_id=OwnerId(UUID(int=2)),
        source_type=SourceType.TEXT,
        captured_at=instant,
        raw_content=raw,
        raw_content_hash=sha256(raw).hexdigest(),
        original_title="Synthetic note",
    )


@pytest.fixture
def processing(content: ContentItem) -> ProcessingIdentity:
    return ProcessingIdentity(
        provider="synthetic",
        model="fixture-model",
        prompt_version="1",
        prompt_hash=sha256(b"synthetic prompt").hexdigest(),
        schema_version="1",
        pipeline_version="1",
        input_hash=content.raw_content_hash,
    )


@pytest.fixture
def evidence(content: ContentItem) -> SourceEvidence:
    return SourceEvidence(
        owner_id=content.owner_id,
        content_id=content.id,
        extraction_id=ExtractionId(UUID(int=3)),
        start=0,
        end=16,
        quote="Reply by Friday.",
    )


@pytest.fixture
def mission(content: ContentItem) -> ResearchMission:
    return ResearchMission(
        id=MissionId(UUID(int=4)),
        owner_id=content.owner_id,
        topic_id=TopicId(UUID(int=5)),
        question="What needs my attention?",
        run_sequence=1,
        status=MissionStatus.RUNNING,
    )


@pytest.fixture
def result(
    mission: ResearchMission,
    instant: datetime,
    processing: ProcessingIdentity,
    evidence: SourceEvidence,
) -> ResearchResult:
    return ResearchResult(
        id=ResultId(UUID(int=6)),
        owner_id=mission.owner_id,
        topic_id=mission.topic_id,
        mission_id=mission.id,
        run_sequence=mission.run_sequence,
        version=1,
        published_at=instant,
        answer="Reply by Friday; exact date is unresolved.",
        processing=processing,
        evidence=(evidence,),
    )


@pytest.fixture
def proposal(processing: ProcessingIdentity, evidence: SourceEvidence) -> ActionProposal:
    return ActionProposal(
        id=ProposalId(UUID(int=7)),
        owner_id=evidence.owner_id,
        title="Reply",
        description="Review the note and reply.",
        candidate_ordinal=0,
        processing=processing,
        evidence=(evidence,),
        origin=ActionOrigin(
            kind=ActionOriginType.SOURCE_ANALYSIS,
            analysis_id=AnalysisId(UUID(int=8)),
        ),
    )
