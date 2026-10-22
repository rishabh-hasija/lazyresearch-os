"""Versioned, provider-neutral Catch Up snapshots. No generated preference labels."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isfinite
from uuid import UUID

from lazyresearch.domain._validation import utc_instant
from lazyresearch.domain.identity import ContentId, OwnerId

FEATURE_VERSION = "catch-up-v1"
LABEL_POLICY = "explicit-feedback-v1"


class Relevance(StrEnum):
    READ = "READ"
    KEEP = "KEEP"
    ACT = "ACT"
    IGNORE = "IGNORE"


CLASSES = tuple(Relevance)


class InteractionKind(StrEnum):
    ITEM_OPENED = "ITEM_OPENED"
    ITEM_IGNORED = "ITEM_IGNORED"
    ITEM_ARCHIVED = "ITEM_ARCHIVED"
    ITEM_SAVED = "ITEM_SAVED"
    ITEM_ACTED_ON = "ITEM_ACTED_ON"
    ITEM_RESURFACED = "ITEM_RESURFACED"
    MISSION_USED_ITEM = "MISSION_USED_ITEM"
    FEEDBACK_LABELED = "FEEDBACK_LABELED"


@dataclass(frozen=True)
class Features:
    # Encoding: URL/PDF/TEXT/MARKDOWN = 0/1/2/3; missing numeric values = -1.
    source_type: int
    age_hours: float
    length: int
    duplicate_count: int
    has_action: bool
    has_deadline: bool
    interest_overlap: float | None
    opened_before: int
    times_resurfaced: int
    analysis_missing: bool
    schema: str = FEATURE_VERSION

    def __post_init__(self) -> None:
        if self.schema != FEATURE_VERSION or self.source_type not in range(4):
            raise ValueError("unsupported feature encoding")
        if not isfinite(self.age_hours) or self.age_hours < 0:
            raise ValueError("invalid age")
        for count in (self.length, self.duplicate_count, self.opened_before, self.times_resurfaced):
            if type(count) is not int or count < 0:
                raise ValueError("invalid feature count")
        if self.interest_overlap is not None and not 0 <= self.interest_overlap <= 1:
            raise ValueError("invalid interest overlap")

    def vector(self) -> tuple[float, ...]:
        return (
            float(self.source_type),
            self.age_hours,
            float(self.length),
            float(self.duplicate_count),
            float(self.has_action),
            float(self.has_deadline),
            -1.0 if self.interest_overlap is None else self.interest_overlap,
            float(self.opened_before),
            float(self.times_resurfaced),
            float(self.analysis_missing),
        )


@dataclass(frozen=True)
class Scores:
    # Exact order is READ, KEEP, ACT, IGNORE; no implicit absent-class remapping.
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", tuple(self.values))
        if len(self.values) != 4 or any(not isfinite(v) or not 0 <= v <= 1 for v in self.values):
            raise ValueError("four finite class probabilities required")
        if abs(sum(self.values) - 1) > 1e-5:
            raise ValueError("probabilities must sum to one")

    @property
    def label(self) -> Relevance:
        return CLASSES[max(range(4), key=lambda i: self.values[i])]

    @property
    def usefulness(self) -> float:
        return self.values[0] + self.values[2] + 0.5 * self.values[1]


@dataclass(frozen=True)
class RankingInput:
    owner_id: OwnerId
    content_id: ContentId
    cutoff: datetime
    features: Features
    groups: tuple[str, ...]
    extraction_id: UUID | None = None
    analysis_id: UUID | None = None
    override: Relevance | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "cutoff", utc_instant(self.cutoff, "cutoff"))
        object.__setattr__(self, "groups", tuple(self.groups))
        if not self.groups:
            raise ValueError("source grouping required")


@dataclass(frozen=True)
class LabeledExample:
    observation_id: UUID
    event_id: UUID
    item: RankingInput
    label: Relevance
    available_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "available_at", utc_instant(self.available_at, "available_at"))
        if self.available_at <= self.item.cutoff:
            raise ValueError("label must follow feature cutoff")


@dataclass(frozen=True)
class RankingDecision:
    id: UUID
    item: RankingInput
    scores: Scores
    label: Relevance
    mode: str
    model_version: str
    context_hash: str
    context_events: tuple[UUID, ...]
    reasons: tuple[str, ...]
    deadline_visible: bool
    evaluation: str | None = None


class RankingUnavailable(Exception):
    """Optional ranking inference unavailable; baseline remains usable."""
