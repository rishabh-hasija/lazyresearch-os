"""Local optional TabPFN v2. Built with PriorLabs-TabPFN.

No checkpoint downloads on application paths. Provision an official local checkpoint
explicitly, then supply its path. Only tabular features enter the predictor.
"""

import os
from hashlib import sha256
from importlib import import_module
from importlib.metadata import version
from pathlib import Path

from lazyresearch.application.relevance_models import (
    CLASSES,
    Features,
    LabeledExample,
    RankingUnavailable,
    Scores,
)


class TabPFNRankingModel:
    def __init__(self, model_path: str) -> None:
        path = Path(model_path).resolve()
        if not path.is_file():
            raise RankingUnavailable("local TabPFN checkpoint required")
        self.path = path
        self.digest = sha256(path.read_bytes()).hexdigest()
        try:
            package = version("tabpfn")
        except Exception as exc:
            raise RankingUnavailable("optional TabPFN package missing") from exc
        if package != "2.2.1":
            raise RankingUnavailable("unvalidated TabPFN version")
        dependencies = ":".join(f"{p}-{version(p)}" for p in ("torch", "scikit-learn", "numpy"))
        self._version = (
            f"tabpfn-{package}:sha256:{self.digest}:cpu:estimators-2:seed-42:v1:{dependencies}"
        )

    @property
    def version(self) -> str:
        return self._version

    def predict(
        self, context: tuple[LabeledExample, ...], features: tuple[Features, ...]
    ) -> tuple[Scores, ...]:
        if not 4 <= len(context) <= 1000 or not 1 <= len(features) <= 1000:
            raise RankingUnavailable("local ranking row budget exceeded")
        if set(r.label for r in context) != set(CLASSES):
            raise RankingUnavailable("four labeled classes required")
        if not self.path.is_file() or sha256(self.path.read_bytes()).hexdigest() != self.digest:
            raise RankingUnavailable("checkpoint changed")
        # Set before importing the optional package. Never transmit telemetry or data.
        os.environ["TABPFN_DISABLE_TELEMETRY"] = "1"
        os.environ["HF_HUB_OFFLINE"] = "1"
        try:
            torch = import_module("torch")
            torch.set_num_threads(4)
            module = import_module("tabpfn")
            model = module.TabPFNClassifier(
                model_path=str(self.path),
                device="cpu",
                n_estimators=2,
                random_state=42,
            )
            model.fit(
                [r.item.features.vector() for r in context],
                [CLASSES.index(r.label) for r in context],
            )
            if set(int(c) for c in model.classes_) != set(range(4)):
                raise ValueError("invalid class mapping")
            output = model.predict_proba([f.vector() for f in features])
            positions = [list(model.classes_).index(i) for i in range(4)]
            result = tuple(Scores(tuple(float(row[p]) for p in positions)) for row in output)
            if len(result) != len(features):
                raise ValueError("invalid prediction count")
            return result
        except Exception as exc:
            raise RankingUnavailable("local TabPFN inference failed") from exc
