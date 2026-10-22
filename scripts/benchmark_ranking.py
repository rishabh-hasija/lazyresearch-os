"""Explicit local generic/demo evaluation; no user data or synthetic personal claim."""

import argparse
import json
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path
from time import perf_counter

from lazyresearch.application.relevance import baseline
from lazyresearch.application.relevance_evaluation import chronological_split, improved, metrics
from lazyresearch.infrastructure.ranking import TabPFNRankingModel
from tests.ranking_helpers import examples


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--output", default="docs/ranking_benchmark_results.json")
    args = parser.parse_args()
    rows = examples()
    train, test = chronological_split(rows)
    model = TabPFNRankingModel(args.model_path)
    start = perf_counter()
    control = tuple(baseline(r.item.features) for r in test)
    baseline_seconds = perf_counter() - start
    start = perf_counter()
    predictions = model.predict(train, tuple(r.item.features for r in test))
    cold_seconds = perf_counter() - start
    start = perf_counter()
    repeated = model.predict(train, tuple(r.item.features for r in test))
    warm_seconds = perf_counter() - start
    actual, simple = metrics(test, predictions), metrics(test, control)
    output = {
        "mode": "GENERIC_DEMO",
        "personalization_claim": False,
        "feature_version": "catch-up-v1",
        "label_policy": "explicit-feedback-v1",
        "fixture": (
            "120 authored synthetic feature rows; four simple scenario families; no user labels"
        ),
        "split": (
            "70/30 chronological by feature cutoff; purge shared source/raw groups and late labels"
        ),
        "train_count": len(train),
        "test_count": len(test),
        "train_events": [str(r.event_id) for r in train],
        "test_events": [str(r.event_id) for r in test],
        "model": model.version,
        "packages": {p: version(p) for p in ("tabpfn", "torch", "scikit-learn", "numpy")},
        "baseline": asdict(simple),
        "tabpfn": asdict(actual),
        "class_order": ["READ", "KEEP", "ACT", "IGNORE"],
        "seconds": {
            "baseline": baseline_seconds,
            "tabpfn_cold": cold_seconds,
            "tabpfn_repeated_refit": warm_seconds,
        },
        "repeat_identical": [s.values for s in predictions] == [s.values for s in repeated],
        "engineering_improvement_gate": improved(actual, simple),
        "rows": [
            {
                "observation": str(r.observation_id),
                "cutoff": r.item.cutoff.isoformat(),
                "groups": r.item.groups,
                "features": asdict(r.item.features),
                "label": r.label.value,
                "baseline": b.values,
                "tabpfn": p.values,
            }
            for r, b, p in zip(test, control, predictions, strict=True)
        ],
        "limits": [
            "Synthetic separable scenarios, not an unbiased relevance benchmark",
            "No confidence interval, real-user generalization or calibration claim",
            "CPU memory/peak RSS not measured; two fits only; no production latency claim",
        ],
    }
    Path(args.output).write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                k: output[k]
                for k in (
                    "mode",
                    "train_count",
                    "test_count",
                    "baseline",
                    "tabpfn",
                    "seconds",
                    "engineering_improvement_gate",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
