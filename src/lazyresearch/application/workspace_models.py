"""Delivery projections, with no ORM or UI types."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from lazyresearch.domain.analysis import ContentAnalysis


@dataclass(frozen=True)
class SourceView:
    id: UUID
    title: str
    source_type: str
    captured_at: datetime
    url: str | None
    extraction_status: str
    text: str
    analysis: ContentAnalysis | None
    processing_status: str
    failed_job: UUID | None = None


@dataclass(frozen=True)
class MissionView:
    id: UUID
    question: str
    status: str
    stage: str
    run_sequence: int
    failure: str | None


@dataclass(frozen=True)
class ResultView:
    id: UUID
    version: int
    run_sequence: int
    published_at: datetime
    coverage: str
    baseline_version: int | None
    payload: dict[str, Any]
