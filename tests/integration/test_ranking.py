from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from lazyresearch.application.analysis import ProcessPendingContent
from lazyresearch.application.analysis_models import AnalysisConfig
from lazyresearch.application.intake_models import IntakeInput
from lazyresearch.application.relevance import CatchUp
from lazyresearch.application.relevance_models import InteractionKind as Kind
from lazyresearch.application.relevance_models import Relevance
from lazyresearch.domain.content import SourceType
from lazyresearch.domain.identity import OwnerId
from lazyresearch.infrastructure.persistence.analysis import SQLAlchemyAnalysisStore
from lazyresearch.infrastructure.persistence.ranking import PostgreSQLRankingStore
from lazyresearch.infrastructure.persistence.ranking_models import (
    InteractionRow,
    RankingObservationRow,
)
from lazyresearch.ports.errors import RepositoryConflict
from tests.analysis_helpers import FakeProcessor

pytestmark = pytest.mark.integration


def saved(service, owner=None, key="ranking", raw=b"Submit by 2026-11-07."):
    owner = owner or OwnerId(uuid4())
    receipt = service.ingest(owner, key, (IntakeInput(source_type=SourceType.TEXT, payload=raw),))
    return owner, receipt.entries[0].content_id


def label(store, decision, value=Relevance.READ, **kwargs):
    event = kwargs.pop("event_id", uuid4())
    store.interact(
        decision.item.owner_id,
        decision.item.content_id,
        event,
        Kind.FEEDBACK_LABELED,
        datetime.now(UTC),
        explicit=True,
        observation_id=decision.id,
        label=value,
        **kwargs,
    )
    return event


def test_real_features_analysis_deadline_pending_and_owner_scope(db, service):
    owner, content = saved(service)
    other, _ = saved(service)
    store = PostgreSQLRankingStore(db)
    (pending,) = CatchUp(store).rank(owner, datetime.now(UTC))
    assert pending.item.features.analysis_missing and "ANALYSIS_PENDING" in pending.reasons
    ProcessPendingContent(
        SQLAlchemyAnalysisStore(db), FakeProcessor(), AnalysisConfig()
    ).process_one(owner)
    (ready,) = CatchUp(store).rank(owner, datetime.now(UTC))
    assert ready.item.analysis_id and ready.item.extraction_id
    assert ready.deadline_visible and ready.label == Relevance.ACT
    assert ready.item.features.has_action and not ready.item.features.analysis_missing
    assert not store.candidates(other, datetime.now(UTC), (), 50, content)
    with Session(db) as s:
        row = s.get(RankingObservationRow, ready.id)
        assert row.payload["features"]["schema"] == "catch-up-v1"
        assert row.payload["mode"] == "BASELINE"


def test_feedback_correction_retry_override_and_reviewed_exclusion(db, service):
    owner, content = saved(service)
    store = PostgreSQLRankingStore(db)
    (decision,) = CatchUp(store).rank(owner, datetime.now(UTC))
    first = label(store, decision)
    assert CatchUp(store).rank(owner, datetime.now(UTC)) == ()
    correction = label(store, decision, Relevance.IGNORE, supersedes=first)
    with pytest.raises(RepositoryConflict):
        label(store, decision, Relevance.ACT, supersedes=first)
    history = store.history(owner, datetime.now(UTC))
    assert len(history) == 1 and history[0].event_id == correction
    assert history[0].label == Relevance.IGNORE
    (overridden,) = CatchUp(store).rank(owner, datetime.now(UTC), content_id=content)
    assert overridden.label == Relevance.IGNORE and "USER_OVERRIDE" in overridden.reasons
    # Exact retry is idempotent, but a changed event with the same ID is not.
    with Session(db) as s:
        e = s.get(InteractionRow, correction)
        occurred = e.occurred_at
    store.interact(
        owner,
        content,
        correction,
        Kind.FEEDBACK_LABELED,
        occurred,
        explicit=True,
        observation_id=decision.id,
        label=Relevance.IGNORE,
        supersedes=first,
    )
    with pytest.raises(RepositoryConflict):
        store.interact(
            owner,
            content,
            correction,
            Kind.FEEDBACK_LABELED,
            occurred,
            explicit=True,
            observation_id=decision.id,
            label=Relevance.ACT,
            supersedes=first,
        )


@pytest.mark.parametrize(
    "kind",
    [
        Kind.ITEM_ARCHIVED,
        Kind.MISSION_USED_ITEM,
        Kind.ITEM_OPENED,
        Kind.ITEM_ACTED_ON,
        Kind.ITEM_IGNORED,
    ],
)
def test_implicit_events_never_become_labels(db, service, kind):
    owner, content = saved(service)
    store = PostgreSQLRankingStore(db)
    store.interact(owner, content, uuid4(), kind, datetime.now(UTC), explicit=False)
    assert store.history(owner, datetime.now(UTC)) == ()
    assert len(CatchUp(store).rank(owner, datetime.now(UTC))) == 1
    with pytest.raises(ValueError):
        store.interact(
            owner, content, uuid4(), kind, datetime.now(UTC), explicit=True, label=Relevance.READ
        )


def test_fixed_cutoff_counts_late_records_and_frozen_features(db, service):
    owner, content = saved(service)
    store = PostgreSQLRankingStore(db)
    cutoff = datetime.now(UTC)
    (before,) = CatchUp(store).rank(owner, cutoff)
    store.interact(
        owner, content, uuid4(), Kind.ITEM_OPENED, cutoff - timedelta(seconds=1), explicit=True
    )
    saved(service, owner, "duplicate")
    (old,) = CatchUp(store).rank(owner, cutoff)
    (new,) = CatchUp(store).rank(owner, datetime.now(UTC))
    assert old.item.features == before.item.features
    assert new.item.features.opened_before == 1 and new.item.features.duplicate_count == 1
    label(store, new)
    assert store.history(owner, cutoff) == ()


def test_cross_owner_observation_event_and_stale_feedback_rejected(db, service):
    owner, content = saved(service)
    other, second = saved(service)
    store = PostgreSQLRankingStore(db)
    (decision,) = CatchUp(store).rank(owner, datetime.now(UTC))
    with pytest.raises(RepositoryConflict):
        store.interact(
            other,
            second,
            uuid4(),
            Kind.FEEDBACK_LABELED,
            datetime.now(UTC),
            explicit=True,
            observation_id=decision.id,
            label=Relevance.READ,
        )
    with pytest.raises(RepositoryConflict):
        store.interact(
            owner,
            content,
            uuid4(),
            Kind.FEEDBACK_LABELED,
            decision.item.cutoff - timedelta(seconds=1),
            explicit=True,
            observation_id=decision.id,
            label=Relevance.ACT,
        )
    with pytest.raises(ValueError):
        store.interact(
            owner,
            content,
            uuid4(),
            Kind.FEEDBACK_LABELED,
            datetime.now(UTC),
            explicit=False,
            observation_id=decision.id,
            label=Relevance.READ,
        )


def test_concurrent_label_corrections_are_fenced(db, service):
    owner, _ = saved(service)
    store = PostgreSQLRankingStore(db)
    (decision,) = CatchUp(store).rank(owner, datetime.now(UTC))
    first = label(store, decision)

    def correct(value):
        try:
            label(PostgreSQLRankingStore(db), decision, value, supersedes=first)
            return True
        except RepositoryConflict:
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(correct, (Relevance.ACT, Relevance.IGNORE)))
    assert sorted(results) == [False, True]
    assert len(store.history(owner, datetime.now(UTC))) == 1


def test_feedback_receipt_order_does_not_compare_separate_clocks(db, service):
    owner, content = saved(service)
    store = PostgreSQLRankingStore(db)
    (decision,) = CatchUp(store).rank(owner, datetime.now(UTC))
    # Occurrence follows the app's feature cutoff, but predates the DB receipt clock.
    occurred = decision.item.cutoff + timedelta(microseconds=1)
    with Session(db) as s:
        row = s.get(RankingObservationRow, decision.id)
        assert occurred < row.recorded_at
    store.interact(
        owner,
        content,
        uuid4(),
        Kind.FEEDBACK_LABELED,
        occurred,
        explicit=True,
        observation_id=decision.id,
        label=Relevance.KEEP,
    )
    assert store.history(owner, datetime.now(UTC))[0].label == Relevance.KEEP


def test_observations_events_immutable_and_migration_roundtrip(db, service):
    owner, _ = saved(service)
    store = PostgreSQLRankingStore(db)
    (decision,) = CatchUp(store).rank(owner, datetime.now(UTC))
    event = label(store, decision)
    for model, identity in ((RankingObservationRow, decision.id), (InteractionRow, event)):
        with pytest.raises(DBAPIError), db.begin() as c:
            c.execute(update(model).where(model.id == identity).values(id=identity))
        with pytest.raises(DBAPIError), db.begin() as c:
            c.execute(model.__table__.delete().where(model.id == identity))
    config = Config("alembic.ini")
    with db.begin() as c:
        config.attributes["connection"] = c
        command.downgrade(config, "0004")
        command.upgrade(config, "head")
        command.check(config)
    assert {"ranking_observation", "user_interaction"} <= set(inspect(db).get_table_names())


@pytest.mark.parametrize("visibility", ["ARCHIVED", "DELETION_PENDING", "DELETED"])
def test_inactive_sources_excluded_and_deleted_history_denied(db, service, visibility):
    owner, content = saved(service)
    store = PostgreSQLRankingStore(db)
    (decision,) = CatchUp(store).rank(owner, datetime.now(UTC))
    label(store, decision)
    with db.begin() as c:
        c.execute(
            text(
                "INSERT INTO retrieval_state(owner_id,content_id,extraction_id,visibility) "
                "VALUES (:o,:c,:e,:v)"
            ),
            {"o": owner, "c": content, "e": decision.item.extraction_id, "v": visibility},
        )
    assert CatchUp(store).rank(owner, datetime.now(UTC), content_id=content) == ()
    assert bool(store.history(owner, datetime.now(UTC))) == (visibility == "ARCHIVED")
    with pytest.raises(RepositoryConflict):
        store.save(replace(decision, id=uuid4()))
