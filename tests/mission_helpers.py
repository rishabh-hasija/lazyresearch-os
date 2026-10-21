"""Synthetic batteries only; fake discovery and synthesis for deterministic missions."""

from datetime import UTC, datetime

from lazyresearch.application.intake_models import FetchedSource
from lazyresearch.application.mission_models import (
    CitedClaim,
    MissionAction,
    ResearchBrief,
    SearchHit,
    SynthesisOutput,
)


class FakeSearch:
    def __init__(self):
        self.calls = []
        self.urls = ["https://example.com/battery-price", "https://example.com/battery-specs"]

    def search(self, query, limit):
        self.calls.append(query)
        return tuple(
            SearchHit(url=url, title="Battery", snippet="UNVERIFIED_SNIPPET_99999", rank=i + 1)
            for i, url in enumerate(self.urls[:limit])
        )


class FakePages:
    def __init__(self):
        self.calls = []
        self.price = "5000"

    def fetch(self, url):
        self.calls.append(url)
        return FetchedSource(
            payload=(
                f"Battery price EUR {self.price}. Battery capacity 10 kWh. "
                "Request an installer assessment by next Friday."
            ).encode(),
            final_url=url,
            fetched_at=datetime.now(UTC),
            http_status=200,
            content_type="text/plain",
        )


class FakeSynthesis:
    def __init__(self):
        self.calls = []
        self.recommendation = "Ask for an installer assessment."

    def synthesize(self, request):
        self.calls.append(request)
        evidence = tuple(e.id for e in request.evidence)
        claim = CitedClaim(
            text="Battery sources support an installer comparison.", evidence=evidence
        )
        return SynthesisOutput(
            brief=ResearchBrief(
                answer=claim,
                summary=claim,
                findings=(claim,),
                recommendations=(CitedClaim(text=self.recommendation, evidence=evidence),),
                action_candidates=(
                    MissionAction(
                        title="Request assessment",
                        description=self.recommendation,
                        evidence=evidence,
                        deadline_raw="next Friday"
                        if any("next Friday" in e.quote for e in request.evidence)
                        else None,
                    ),
                ),
            ),
            provider="fake",
            model="fixture-v1",
            model_revision=None,
            runtime=None,
            prompt_hash="a" * 64,
            latency_seconds=0.01,
            repaired=False,
        )


def prepare(ops, owner, mission):
    ops.store.start(owner, mission)
    ops.personal_search(owner, mission)
    for i in range(ops.gap_detection(owner, mission)):
        ops.public_search(owner, mission, i, final_attempt=True)
    for i in range(ops.select_sources(owner, mission)):
        ops.fetch_source(owner, mission, i, final_attempt=True)
        ops.process_source(owner, mission, i)
    ops.freeze_evidence(owner, mission)
    ops.detect_contradictions(owner, mission)
    ops.synthesize(owner, mission)
    ops.validate(owner, mission)
