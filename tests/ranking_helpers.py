"""Synthetic generic examples; never imported by production ranking."""

from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from lazyresearch.application.relevance_models import (
    CLASSES,
    Features,
    LabeledExample,
    RankingInput,
)
from lazyresearch.domain.identity import ContentId, OwnerId

OWNER = OwnerId(uuid5(NAMESPACE_URL, "catch-up-demo-owner"))


def examples(n: int = 120) -> tuple[LabeledExample, ...]:
    result = []
    for i in range(n):
        label = CLASSES[i % 4]
        # Four authored scenario families: substantial reading, reference material,
        # explicit tasks, and short repetitive notices. Deliberately simple fixture.
        length = (6000, 18000, 1200, 100)[i % 4] + (i // 4 % 7) * 13
        features = Features(
            i % 3,
            float(120 + i % 17),
            length,
            1 if i % 4 == 3 and i % 8 == 3 else 0,
            i % 4 == 2,
            i % 12 == 2,
            None,
            i % 3,
            i % 2,
            False,
        )
        cutoff = datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=i)
        content = ContentId(uuid5(NAMESPACE_URL, f"demo-content-{i}"))
        item = RankingInput(OWNER, content, cutoff, features, (f"fixture-group-{i}",))
        result.append(
            LabeledExample(
                uuid5(NAMESPACE_URL, f"demo-observation-{i}"),
                uuid5(NAMESPACE_URL, f"demo-event-{i}"),
                item,
                label,
                cutoff + timedelta(minutes=1),
            )
        )
    return tuple(result)
