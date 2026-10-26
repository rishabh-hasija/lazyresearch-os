"""Catch Up uses frozen features and explicit labels; never changes source visibility."""

import json
from dataclasses import asdict
from datetime import datetime
from hashlib import sha256
from uuid import UUID, uuid4

from lazyresearch.application.relevance_evaluation import (
    chronological_split,
    connected_groups,
    improved,
    metrics,
    sufficient,
)
from lazyresearch.application.relevance_models import (
    Features,
    RankingDecision,
    RankingUnavailable,
    Relevance,
    Scores,
)
from lazyresearch.domain._validation import utc_instant
from lazyresearch.domain.identity import ContentId, OwnerId
from lazyresearch.ports.ranking import RankingModel, RankingStore

BASELINE_VERSION = "rules-v1"


def baseline(features: Features) -> Scores:
    if features.has_action or features.has_deadline:
        return Scores((0.1, 0.1, 0.75, 0.05))
    if features.duplicate_count > 0:
        return Scores((0.1, 0.2, 0.05, 0.65))
    if features.interest_overlap is not None and features.interest_overlap > 0:
        return Scores((0.65, 0.25, 0.05, 0.05))
    if features.age_hours <= 72:
        return Scores((0.55, 0.3, 0.05, 0.1))
    return Scores((0.2, 0.6, 0.05, 0.15))


class CatchUp:
    def __init__(
        self,
        store: RankingStore,
        model: RankingModel | None = None,
        *,
        unavailable: bool = False,
    ) -> None:
        self.store, self.model = store, model
        self.unavailable = unavailable

    def rank(
        self,
        owner: OwnerId,
        cutoff: datetime,
        *,
        interests: tuple[str, ...] = (),
        limit: int = 50,
        content_id: ContentId | None = None,
        collection_id: UUID | None = None,
    ) -> tuple[RankingDecision, ...]:
        cutoff = utc_instant(cutoff, "cutoff")
        if not 1 <= limit <= 100 or len(interests) > 20:
            raise ValueError("ranking request exceeds bounds")
        if any(not t.strip() or len(t) > 100 for t in interests):
            raise ValueError("invalid interest")
        items = self.store.candidates(owner, cutoff, interests, limit, content_id, collection_id)
        if any(i.owner_id != owner or i.cutoff != cutoff for i in items):
            raise ValueError("invalid scoped ranking inputs")
        if not items:
            return ()
        groups = {g for item in items for g in item.groups}
        eligible = tuple(
            r
            for r in self.store.history(owner, cutoff)
            if r.item.owner_id == owner and r.available_at < cutoff
        )
        groups = connected_groups(eligible, groups)
        history = tuple(r for r in eligible if not groups.intersection(r.item.groups))[-1000:]
        predictions = tuple(baseline(item.features) for item in items)
        mode, version, reason, evaluation = "BASELINE", BASELINE_VERSION, "COLD_START", None
        train, test = chronological_split(history)
        if self.model is not None and sufficient(train) and len(test) >= 20:
            try:
                heldout = self.model.predict(train, tuple(r.item.features for r in test))
                actual = metrics(test, heldout)
                control = metrics(test, tuple(baseline(r.item.features) for r in test))
                evaluation = json.dumps(
                    {
                        "model": asdict(actual),
                        "baseline": asdict(control),
                        "model_version": self.model.version,
                        "train_events": [str(r.event_id) for r in train],
                        "test_events": [str(r.event_id) for r in test],
                    },
                    sort_keys=True,
                )
                if improved(actual, control):
                    predictions = self.model.predict(history, tuple(i.features for i in items))
                    if len(predictions) != len(items):
                        raise ValueError("unaligned model output")
                    mode, version, reason = "PERSONAL", self.model.version, "EVALUATED_CONTEXT"
                else:
                    reason = "NO_HELDOUT_IMPROVEMENT"
            except (RankingUnavailable, ValueError):
                reason = "MODEL_UNAVAILABLE_OR_INVALID"
        elif self.model is None:
            reason = "MODEL_UNAVAILABLE" if self.unavailable else "MODEL_DISABLED"
        payload = {
            "policy": "explicit-feedback-v1",
            "features": "catch-up-v1",
            "model": version,
            "events": [str(r.event_id) for r in history],
        }
        context_hash = sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        decisions = []
        for item, scores in zip(items, predictions, strict=True):
            reasons = [reason]
            label = scores.label
            if item.features.has_deadline:
                reasons.append("POTENTIAL_DEADLINE")
            if item.features.has_action:
                reasons.append("SOURCE_ACTION")
            if item.features.duplicate_count:
                reasons.append("REPETITIVE")
            if item.features.analysis_missing:
                reasons.append("ANALYSIS_PENDING")
            if mode == "BASELINE":
                if scores.label == Relevance.READ:
                    reasons.append("INTEREST_MATCH" if item.features.interest_overlap else "RECENT")
                elif scores.label == Relevance.KEEP:
                    reasons.append("OLDER_REFERENCE")
                elif scores.label == Relevance.IGNORE:
                    reasons.append("LOW_RELEVANCE_SUGGESTION")
            if item.override is not None:
                label = item.override
                reasons.append("USER_OVERRIDE")
            elif item.features.has_deadline:
                label = Relevance.ACT
            decision = RankingDecision(
                uuid4(),
                item,
                scores,
                label,
                mode,
                version,
                context_hash,
                tuple(r.event_id for r in history),
                tuple(reasons),
                item.features.has_deadline,
                evaluation,
            )
            self.store.save(decision)
            decisions.append(decision)
        return tuple(
            sorted(
                decisions,
                key=lambda d: (
                    not d.deadline_visible,
                    -d.scores.usefulness,
                    str(d.item.content_id),
                ),
            )
        )
