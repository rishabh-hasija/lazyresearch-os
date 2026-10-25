"""Explicit worker/reconciler entry point. Reads environment; never migrates or starts services."""

import asyncio

from lazyresearch.bootstrap import build_research
from lazyresearch.infrastructure.config import Settings
from lazyresearch.infrastructure.persistence.missions import PostgreSQLMissionStore
from lazyresearch.infrastructure.workflows.connection import connect_temporal
from lazyresearch.infrastructure.workflows.runtime import reconcile, research_worker


async def main() -> None:
    settings = Settings.from_env()
    client = await connect_temporal(settings)
    operations = build_research(settings)
    assert isinstance(operations.store, PostgreSQLMissionStore)
    async with research_worker(client, operations, settings.temporal_task_queue):
        while True:
            await reconcile(client, operations.store, settings.temporal_task_queue)
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
