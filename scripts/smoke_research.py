"""Small synthetic mission using real Gemma, PostgreSQL and optionally Temporal/SerpApi."""

import asyncio
import json
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from temporalio.client import Client

from lazyresearch.application.intake_models import IntakeInput
from lazyresearch.application.mission_models import MissionScope
from lazyresearch.bootstrap import build_research
from lazyresearch.domain.content import SourceType
from lazyresearch.domain.identity import OwnerId
from lazyresearch.infrastructure.config import Settings
from lazyresearch.infrastructure.persistence.missions import PostgreSQLMissionStore
from lazyresearch.infrastructure.workflows.runtime import reconcile, research_worker


async def main() -> None:
    settings = Settings.from_env()
    operations = build_research(settings)
    store = operations.store
    assert isinstance(store, PostgreSQLMissionStore)
    owner = OwnerId(uuid4())
    for i, source in enumerate(
        (
            "Battery installer quote: the HomeCell system costs EUR 5000 for 10 kWh. "
            "Request a site assessment by 2026-11-07.",
            "Battery comparison note: HomeCell stores 10 kWh. A separate installer quotes "
            "EUR 5500 including installation. Confirm installation scope before comparing costs.",
        )
    ):
        operations.intake.ingest(
            owner,
            f"smoke-{i}",
            (IntakeInput(source_type=SourceType.TEXT, payload=source.encode()),),
        )
    topic = store.create_topic(owner, "Synthetic home battery smoke")
    mission = store.create_mission(owner, topic.id, "Battery", MissionScope(max_evidence=4))
    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
    queue = "lr-smoke-" + uuid4().hex
    started = perf_counter()
    async with research_worker(client, operations, queue):
        await reconcile(client, store, queue)
        result_id = await client.get_workflow_handle(str(mission.id)).result()
    output = store.stage(owner, mission.id, "synthesize")
    assert output is not None
    store.validate_evidence(owner, mission.id)
    report = {
        "mission_seconds": perf_counter() - started,
        "model": settings.ai.model,
        "runtime": output["runtime"],
        "evidence_count": len(store.evidence(owner, mission.id)),
        "synthesis_seconds": output["latency_seconds"],
        "repaired": output["repaired"],
        "citation_validation": "passed",
        "result_id": result_id,
        "temporal": "completed",
        "output": output,
    }
    if settings.serpapi_api_key:
        search_start = perf_counter()
        hits = operations.search.search("home battery energy storage specifications", 1)
        fetched = failed = 0
        for hit in hits[:1]:
            receipt = operations.intake.ingest(
                owner, "serpapi-smoke", (IntakeInput(source_type=SourceType.URL, url=hit.url),)
            )
            fetched += receipt.saved
            failed += receipt.failed
        report["serpapi"] = {
            "queries": 1,
            "hits": len(hits),
            "fetched": fetched,
            "failed": failed,
            "seconds": perf_counter() - search_start,
        }
    else:
        report["serpapi"] = {"status": "skipped_missing_credentials"}
    Path("docs/research_mission_smoke.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in report.items() if k != "output"}))


if __name__ == "__main__":
    asyncio.run(main())
