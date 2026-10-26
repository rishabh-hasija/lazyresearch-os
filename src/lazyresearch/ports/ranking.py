"""Narrow ranking and observation/feedback contracts."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from lazyresearch.application.relevance_models import (
    Features,
    InteractionKind,
    LabeledExample,
    RankingDecision,
    RankingInput,
    Relevance,
    Scores,
)
from lazyresearch.domain.identity import ContentId, OwnerId


class RankingModel(Protocol):
    @property
    def version(self) -> str: ...

    def predict(
        self, context: tuple[LabeledExample, ...], features: tuple[Features, ...]
    ) -> tuple[Scores, ...]: ...


class RankingStore(Protocol):
    def candidates(
        self,
        owner: OwnerId,
        cutoff: datetime,
        interests: tuple[str, ...],
        limit: int,
        content_id: ContentId | None = None,
        collection_id: UUID | None = None,
    ) -> tuple[RankingInput, ...]: ...

    def history(self, owner: OwnerId, cutoff: datetime) -> tuple[LabeledExample, ...]: ...

    def save(self, decision: RankingDecision) -> None: ...

    def interact(
        self,
        owner: OwnerId,
        content: ContentId,
        event_id: UUID,
        kind: InteractionKind,
        occurred_at: datetime,
        *,
        explicit: bool,
        observation_id: UUID | None = None,
        label: Relevance | None = None,
        supersedes: UUID | None = None,
    ) -> None: ...
