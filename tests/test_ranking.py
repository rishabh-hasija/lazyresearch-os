from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from lazyresearch.application.relevance import CatchUp, baseline
from lazyresearch.application.relevance_evaluation import (
    chronological_split,
    improved,
    metrics,
    sufficient,
)
from lazyresearch.application.relevance_models import (
    CLASSES,
    RankingUnavailable,
    Relevance,
    Scores,
)
from lazyresearch.domain.identity import OwnerId
from lazyresearch.infrastructure.ranking import TabPFNRankingModel
from tests.ranking_helpers import OWNER, examples


class MemoryStore:
    def __init__(self, history=()):
        self.rows = history
        self.item = replace(
            examples(1)[0].item, cutoff=datetime(2026, 1, 1, tzinfo=UTC), groups=("candidate",)
        )
        self.saved = []

    def candidates(self, owner, cutoff, interests, limit, content_id=None, collection_id=None):
        return (replace(self.item, cutoff=cutoff),)

    def history(self, owner, cutoff):
        return self.rows

    def save(self, decision):
        self.saved.append(decision)


class Oracle:
    version = "fixture-oracle"

    def predict(self, context, features):
        self.context = context
        result = []
        for f in features:
            index = (
                0
                if f.length > 5000 and f.length < 10000
                else (1 if f.length >= 10000 else 2 if f.has_action else 3)
            )
            result.append(Scores(tuple(1.0 if i == index else 0.0 for i in range(4))))
        return tuple(result)


@pytest.mark.parametrize(
    "values", [(1, 0, 0), (1, 1, 0, 0), (float("nan"), 0, 0, 0), (-0.1, 0.5, 0.3, 0.3)]
)
def test_invalid_scores(values):
    with pytest.raises(ValueError):
        Scores(values)


def test_features_are_versioned_finite_and_fixed():
    f = examples(1)[0].item.features
    assert f.vector()[6] == -1
    for kwargs in (
        {"schema": "future"},
        {"age_hours": float("nan")},
        {"length": -1},
        {"interest_overlap": 2},
        {"source_type": 5},
    ):
        with pytest.raises(ValueError):
            replace(f, **kwargs)


def test_baseline_is_transparent_and_model_not_called_at_cold_start():
    class Never:
        def predict(self, *args):
            pytest.fail("cold start called model")

    store = MemoryStore(examples(20))
    (decision,) = CatchUp(store, Never()).rank(OWNER, store.item.cutoff)
    assert decision.mode == "BASELINE" and "COLD_START" in decision.reasons
    assert decision.scores == baseline(store.item.features)
    assert store.saved == [decision]


def test_missing_class_and_small_history_gate():
    rows = examples()
    assert sufficient(rows)
    assert not sufficient(rows[:39])
    assert not sufficient(tuple(r for r in rows if r.label != Relevance.ACT))


def test_chronology_groups_and_late_labels_are_purged():
    rows = list(examples())
    rows[0] = replace(rows[0], item=replace(rows[0].item, groups=rows[-1].item.groups))
    rows[1] = replace(rows[1], available_at=rows[-1].available_at)
    train, test = chronological_split(tuple(rows))
    assert rows[0] not in train and rows[1] not in train
    assert max(r.available_at for r in train) < min(r.item.cutoff for r in test)
    assert not {g for r in train for g in r.item.groups} & {g for r in test for g in r.item.groups}


def test_metrics_perfect_and_absent_classes_are_explicit():
    rows = examples(20)
    scores = tuple(Scores(tuple(float(r.label == c) for c in CLASSES)) for r in rows)
    m = metrics(rows, scores)
    assert m.macro_f1 == 1 and m.recall == (1, 1, 1, 1) and m.counts == (5, 5, 5, 5)
    assert m.top5_usefulness == 1
    assert not improved(m, m)
    absent = metrics(rows[:1], scores[:1])
    assert absent.macro_f1 == 0.25 and absent.recall[2] == 0


def test_transitive_duplicate_bridge_is_purged():
    rows = list(examples())
    rows[0] = replace(rows[0], item=replace(rows[0].item, groups=("raw-a", "source-x")))
    rows[1] = replace(rows[1], item=replace(rows[1].item, groups=("raw-b", "source-x")))
    rows[-1] = replace(rows[-1], item=replace(rows[-1].item, groups=("raw-b", "source-y")))
    train, _ = chronological_split(tuple(rows))
    assert rows[0] not in train and rows[1] not in train


def test_evaluated_personal_context_and_immutable_hash():
    store = MemoryStore(examples())
    model = Oracle()
    (decision,) = CatchUp(store, model).rank(OWNER, store.item.cutoff)
    assert decision.mode == "PERSONAL" and decision.model_version == model.version
    assert decision.evaluation is not None and len(decision.context_hash) == 64
    assert len(model.context) == 120


@pytest.mark.parametrize("failure", ["unavailable", "invalid", "no_improvement"])
def test_fallback_after_failed_evaluation(failure):
    class Bad(Oracle):
        def predict(self, context, features):
            if failure == "unavailable":
                raise RankingUnavailable("safe")
            if failure == "invalid":
                return ()
            return tuple(baseline(f) for f in features)

    store = MemoryStore(examples())
    (decision,) = CatchUp(store, Bad()).rank(OWNER, store.item.cutoff)
    assert decision.mode == "BASELINE"


def test_future_foreign_and_self_group_history_excluded():
    store = MemoryStore(examples())
    store.rows += (
        replace(store.rows[0], event_id=uuid4(), available_at=store.item.cutoff),
        replace(
            store.rows[1],
            event_id=uuid4(),
            item=replace(store.rows[1].item, owner_id=OwnerId(uuid4())),
        ),
        replace(
            store.rows[2],
            event_id=uuid4(),
            item=replace(store.rows[2].item, groups=store.item.groups),
        ),
    )
    model = Oracle()
    (decision,) = CatchUp(store, model).rank(OWNER, store.item.cutoff)
    assert len(decision.context_events) == 120


def test_override_dominates_deadline_but_deadline_remains_visible():
    store = MemoryStore()
    store.item = replace(
        store.item,
        features=replace(store.item.features, has_deadline=True),
        override=Relevance.IGNORE,
    )
    (decision,) = CatchUp(store).rank(OWNER, store.item.cutoff)
    assert decision.label == Relevance.IGNORE and decision.deadline_visible
    assert {"USER_OVERRIDE", "POTENTIAL_DEADLINE"} <= set(decision.reasons)
    store.item = replace(store.item, override=None)
    assert CatchUp(store).rank(OWNER, store.item.cutoff)[0].label == Relevance.ACT


def test_invalid_scope_bounds_and_naive_cutoff():
    store = MemoryStore()
    for kwargs in ({"limit": 101}, {"interests": ("",)}):
        with pytest.raises(ValueError):
            CatchUp(store).rank(OWNER, store.item.cutoff, **kwargs)
    with pytest.raises(ValueError):
        CatchUp(store).rank(OwnerId(uuid4()), store.item.cutoff)
    with pytest.raises(ValueError):
        CatchUp(store).rank(OWNER, datetime(2026, 1, 1))


def test_tabpfn_missing_checkpoint_fails_without_download(tmp_path):
    with pytest.raises(RankingUnavailable):
        TabPFNRankingModel(str(tmp_path / "missing.ckpt"))


def test_label_cannot_precede_features():
    row = examples(1)[0]
    with pytest.raises(ValueError):
        replace(row, available_at=row.item.cutoff - timedelta(seconds=1))


def test_unavailable_bootstrap_fallback_is_visible():
    store = MemoryStore()
    (decision,) = CatchUp(store, unavailable=True).rank(OWNER, store.item.cutoff)
    assert decision.mode == "BASELINE" and "MODEL_UNAVAILABLE" in decision.reasons


def test_tabpfn_adapter_maps_columns_and_rejects_missing_class(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import lazyresearch.infrastructure.ranking as adapter

    checkpoint = tmp_path / "official-test-double.ckpt"
    checkpoint.write_bytes(b"test-double-never-loaded")
    monkeypatch.setattr(adapter, "version", lambda name: "2.2.1")

    class Estimator:
        classes_ = [3, 1, 0, 2]

        def __init__(self, **kwargs):
            assert kwargs["device"] == "cpu"

        def fit(self, x, y):
            assert set(y) == {0, 1, 2, 3} and len(x) == len(y)

        def predict_proba(self, x):
            return [[0.1, 0.2, 0.6, 0.1] for _ in x]

    monkeypatch.setattr(
        adapter,
        "import_module",
        lambda name: (
            SimpleNamespace(set_num_threads=lambda n: None)
            if name == "torch"
            else SimpleNamespace(TabPFNClassifier=Estimator)
        ),
    )
    model = adapter.TabPFNRankingModel(str(checkpoint))
    (result,) = model.predict(examples(4), (examples(1)[0].item.features,))
    assert result.values == (0.6, 0.2, 0.1, 0.1)
    with pytest.raises(RankingUnavailable):
        model.predict(examples(3), (examples(1)[0].item.features,))
    checkpoint.write_bytes(b"modified")
    with pytest.raises(RankingUnavailable):
        model.predict(examples(4), (examples(1)[0].item.features,))
