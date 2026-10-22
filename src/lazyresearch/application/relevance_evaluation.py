"""Chronological, duplicate-group-purged evaluation with fixed four-class metrics."""

from collections import Counter
from dataclasses import dataclass

from lazyresearch.application.relevance_models import CLASSES, LabeledExample, Scores


def sufficient(rows: tuple[LabeledExample, ...]) -> bool:
    counts = Counter(row.label for row in rows)
    return len(rows) >= 40 and all(counts[c] >= 5 for c in CLASSES)


def connected_groups(rows: tuple[LabeledExample, ...], groups: set[str]) -> set[str]:
    """Close over raw-content/source aliases, including transitive duplicate bridges."""
    groups = set(groups)
    changed = True
    while changed:
        changed = False
        for row in rows:
            if groups.intersection(row.item.groups) and not set(row.item.groups) <= groups:
                groups.update(row.item.groups)
                changed = True
    return groups


def chronological_split(
    rows: tuple[LabeledExample, ...],
) -> tuple[tuple[LabeledExample, ...], tuple[LabeledExample, ...]]:
    rows = tuple(sorted(rows, key=lambda r: (r.item.cutoff, str(r.observation_id))))
    boundary = int(len(rows) * 0.7)
    test = rows[boundary:]
    if not test:
        return (), ()
    cutoff = test[0].item.cutoff
    groups = connected_groups(rows, {g for row in test for g in row.item.groups})
    # A label available after the first held-out prediction is future information.
    train = tuple(
        r
        for r in rows[:boundary]
        if r.available_at < cutoff and not groups.intersection(r.item.groups)
    )
    return train, test


@dataclass(frozen=True)
class Metrics:
    macro_f1: float
    recall: tuple[float, ...]
    top5_usefulness: float
    counts: tuple[int, ...]


def metrics(rows: tuple[LabeledExample, ...], predictions: tuple[Scores, ...]) -> Metrics:
    if not rows or len(rows) != len(predictions):
        raise ValueError("nonempty aligned evaluation required")
    recalls, f1s, counts = [], [], []
    for c in CLASSES:
        tp = sum(r.label == c and p.label == c for r, p in zip(rows, predictions, strict=True))
        actual = sum(r.label == c for r in rows)
        predicted = sum(p.label == c for p in predictions)
        counts.append(actual)
        recalls.append(tp / actual if actual else 0.0)
        f1s.append(2 * tp / (actual + predicted) if actual + predicted else 0.0)
    ordered = sorted(
        zip(rows, predictions, strict=True),
        key=lambda pair: (-pair[1].usefulness, str(pair[0].observation_id)),
    )[:5]
    useful = sum(
        1.0 if r.label.value in {"READ", "ACT"} else 0.5 if r.label.value == "KEEP" else 0.0
        for r, _ in ordered
    ) / len(ordered)
    return Metrics(sum(f1s) / 4, tuple(recalls), useful, tuple(counts))


def improved(candidate: Metrics, baseline: Metrics) -> bool:
    # Conservative engineering gate, not statistical evidence of generalization.
    return (
        all(n >= 2 for n in candidate.counts)
        and candidate.macro_f1 > baseline.macro_f1
        and candidate.recall[2] >= baseline.recall[2]
        and candidate.top5_usefulness >= baseline.top5_usefulness
    )
