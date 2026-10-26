"""PostgreSQL features use only information recorded before the prediction cutoff."""

from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Engine, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from lazyresearch.application.relevance_models import (
    Features,
    InteractionKind,
    LabeledExample,
    RankingDecision,
    RankingInput,
    Relevance,
)
from lazyresearch.domain._validation import utc_instant
from lazyresearch.domain.identity import ContentId, OwnerId
from lazyresearch.infrastructure.persistence.models import (
    ActionProposalRow,
    CaptureRow,
    ContentAnalysisRow,
    ContentRow,
    ExtractionRow,
)
from lazyresearch.infrastructure.persistence.ranking_models import (
    InteractionRow,
    RankingObservationRow,
)
from lazyresearch.infrastructure.persistence.retrieval_models import (
    MembershipRow,
    RetrievalStateRow,
)
from lazyresearch.ports.errors import RepositoryConflict, RepositoryError


def restore(row: RankingObservationRow, override: Relevance | None = None) -> RankingInput:
    return RankingInput(
        OwnerId(row.owner_id),
        ContentId(row.content_id),
        row.cutoff,
        Features(**row.payload["features"]),
        tuple(row.payload["groups"]),
        row.extraction_id,
        row.analysis_id,
        override,
    )


class PostgreSQLRankingStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def candidates(
        self,
        owner: OwnerId,
        cutoff: datetime,
        interests: tuple[str, ...],
        limit: int,
        content_id: ContentId | None = None,
        collection_id: UUID | None = None,
    ) -> tuple[RankingInput, ...]:
        cutoff = utc_instant(cutoff, "cutoff")
        if cutoff > datetime.now(UTC) or not 1 <= limit <= 100:
            raise ValueError("invalid candidate request")
        with Session(self.engine) as s:
            query = (
                select(ContentRow)
                .outerjoin(
                    RetrievalStateRow,
                    (
                        (RetrievalStateRow.owner_id == ContentRow.owner_id)
                        & (RetrievalStateRow.content_id == ContentRow.id)
                    ),
                )
                .where(
                    ContentRow.owner_id == owner,
                    ContentRow.created_at < cutoff,
                    (RetrievalStateRow.visibility.is_(None))
                    | (RetrievalStateRow.visibility == "ACTIVE"),
                )
            )
            if collection_id is not None:
                query = query.where(
                    select(MembershipRow.content_id)
                    .where(
                        MembershipRow.owner_id == owner,
                        MembershipRow.content_id == ContentRow.id,
                        MembershipRow.collection_id == collection_id,
                    )
                    .exists()
                )
            if content_id is not None:
                query = query.where(ContentRow.id == content_id)
            else:
                query = query.where(
                    ~select(InteractionRow.id)
                    .where(
                        InteractionRow.owner_id == owner,
                        InteractionRow.content_id == ContentRow.id,
                        InteractionRow.label.is_not(None),
                        InteractionRow.recorded_at < cutoff,
                        InteractionRow.occurred_at < cutoff,
                    )
                    .exists()
                )
            contents = s.scalars(
                query.order_by(ContentRow.created_at.desc(), ContentRow.id).limit(limit)
            ).all()
            result = []
            for c in contents:
                events = list(
                    s.scalars(
                        select(InteractionRow)
                        .where(
                            InteractionRow.owner_id == owner,
                            InteractionRow.content_id == c.id,
                            InteractionRow.recorded_at < cutoff,
                            InteractionRow.occurred_at < cutoff,
                        )
                        .order_by(InteractionRow.recorded_at, InteractionRow.id)
                    )
                )
                labels = [e for e in events if e.label is not None]
                extraction = s.scalar(
                    select(ExtractionRow)
                    .where(
                        ExtractionRow.owner_id == owner,
                        ExtractionRow.content_id == c.id,
                        ExtractionRow.created_at < cutoff,
                    )
                    .order_by(ExtractionRow.created_at.desc(), ExtractionRow.id.desc())
                    .limit(1)
                )
                analysis = None
                if extraction is not None and extraction.status == "SUCCEEDED":
                    analysis = s.scalar(
                        select(ContentAnalysisRow)
                        .where(
                            ContentAnalysisRow.owner_id == owner,
                            ContentAnalysisRow.content_id == c.id,
                            ContentAnalysisRow.extraction_id == extraction.id,
                            ContentAnalysisRow.created_at < cutoff,
                        )
                        .order_by(
                            ContentAnalysisRow.created_at.desc(), ContentAnalysisRow.id.desc()
                        )
                        .limit(1)
                    )
                actions = (
                    []
                    if analysis is None
                    else list(
                        s.scalars(
                            select(ActionProposalRow).where(
                                ActionProposalRow.owner_id == owner,
                                ActionProposalRow.analysis_id == analysis.id,
                            )
                        )
                    )
                )
                captures = (
                    s.scalar(
                        select(func.count())
                        .select_from(CaptureRow)
                        .where(
                            CaptureRow.owner_id == owner,
                            CaptureRow.content_id == c.id,
                            CaptureRow.recorded_at < cutoff,
                        )
                    )
                    or 0
                )
                words = set(t.casefold() for t in analysis.topics) if analysis else set()
                wanted = set(t.casefold() for t in interests)
                features = Features(
                    ("URL", "PDF", "TEXT", "MARKDOWN").index(c.source_type),
                    max(0.0, (cutoff - c.captured_at).total_seconds() / 3600),
                    len(extraction.text) if extraction else 0,
                    max(0, captures - 1),
                    bool(actions),
                    any(a.deadline_raw for a in actions),
                    len(words & wanted) / len(wanted) if wanted else None,
                    sum(e.kind == "ITEM_OPENED" and e.explicit for e in events),
                    sum(e.kind == "ITEM_RESURFACED" for e in events),
                    analysis is None,
                )
                groups = ["raw:" + c.raw_content_hash]
                if c.source_type == "URL":
                    groups.append("source:" + c.source_key)
                result.append(
                    RankingInput(
                        owner,
                        ContentId(c.id),
                        cutoff,
                        features,
                        tuple(groups),
                        extraction.id if extraction else None,
                        analysis.id if analysis else None,
                        Relevance(labels[-1].label or "") if labels else None,
                    )
                )
            return tuple(result)

    def history(self, owner: OwnerId, cutoff: datetime) -> tuple[LabeledExample, ...]:
        with Session(self.engine) as s:
            events = list(
                s.scalars(
                    select(InteractionRow)
                    .where(
                        InteractionRow.owner_id == owner,
                        InteractionRow.label.is_not(None),
                        InteractionRow.occurred_at < cutoff,
                        InteractionRow.recorded_at < cutoff,
                    )
                    .order_by(InteractionRow.recorded_at, InteractionRow.id)
                )
            )
            latest = {event.content_id: event for event in events}
            result = []
            for e in latest.values():
                state = s.get(RetrievalStateRow, (owner, e.content_id))
                if state is not None and state.visibility in {"DELETED", "DELETION_PENDING"}:
                    continue
                row = s.scalar(
                    select(RankingObservationRow).where(
                        RankingObservationRow.id == e.observation_id,
                        RankingObservationRow.owner_id == owner,
                    )
                )
                if row is not None:
                    result.append(
                        LabeledExample(
                            row.id,
                            e.id,
                            restore(row),
                            Relevance(e.label or ""),
                            max(e.occurred_at, e.recorded_at),
                        )
                    )
            return tuple(sorted(result, key=lambda r: (r.available_at, str(r.event_id))))

    def save(self, decision: RankingDecision) -> None:
        item = decision.item
        try:
            with Session(self.engine) as s, s.begin():
                state = s.get(
                    RetrievalStateRow, (item.owner_id, item.content_id), with_for_update=True
                )
                if state is not None and state.visibility != "ACTIVE":
                    raise RepositoryConflict("source became unavailable during ranking")
                s.add(
                    RankingObservationRow(
                        id=decision.id,
                        owner_id=item.owner_id,
                        content_id=item.content_id,
                        extraction_id=item.extraction_id,
                        analysis_id=item.analysis_id,
                        cutoff=item.cutoff,
                        payload={
                            "features": asdict(item.features),
                            "groups": list(item.groups),
                            "scores": decision.scores.values,
                            "label": decision.label.value,
                            "mode": decision.mode,
                            "model_version": decision.model_version,
                            "context_hash": decision.context_hash,
                            "context_events": [str(v) for v in decision.context_events],
                            "reasons": decision.reasons,
                            "deadline_visible": decision.deadline_visible,
                            "evaluation": decision.evaluation,
                            "label_policy": "explicit-feedback-v1",
                        },
                    )
                )
        except SQLAlchemyError as exc:
            raise RepositoryError("ranking observation write failed") from exc

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
    ) -> None:
        occurred_at = utc_instant(occurred_at, "occurred_at")
        if occurred_at > datetime.now(UTC):
            raise ValueError("future interaction")
        if (kind == InteractionKind.FEEDBACK_LABELED) != (label is not None):
            raise ValueError("only explicit feedback supplies a label")
        if label is not None and (not explicit or observation_id is None):
            raise ValueError("label needs explicit feedback on an observation")
        values = dict(
            owner_id=owner,
            content_id=content,
            kind=kind.value,
            explicit=explicit,
            observation_id=observation_id,
            label=label.value if label else None,
            supersedes=supersedes,
            occurred_at=occurred_at,
        )
        try:
            with Session(self.engine) as s, s.begin():
                # Serializes corrections and concurrent duplicate event submissions per content.
                source = s.scalar(
                    select(ContentRow)
                    .where(ContentRow.owner_id == owner, ContentRow.id == content)
                    .with_for_update()
                )
                if source is None:
                    raise RepositoryConflict("source unavailable")
                state = s.get(RetrievalStateRow, (owner, content), with_for_update=True)
                if state is not None and state.visibility in {"DELETED", "DELETION_PENDING"}:
                    raise RepositoryConflict("source unavailable")
                existing = s.get(InteractionRow, event_id)
                if existing is not None:
                    if any(getattr(existing, k) != v for k, v in values.items()):
                        raise RepositoryConflict("event identity conflict")
                    return
                s.add(InteractionRow(id=event_id, **values))
        except SQLAlchemyError as exc:
            raise RepositoryConflict("invalid interaction or stale correction") from exc
