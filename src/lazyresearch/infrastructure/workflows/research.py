"""Replay-safe v1 workflow: IDs and bounded counts only, no application imports."""

import asyncio
from datetime import timedelta
from typing import cast

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, CancelledError

RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    maximum_interval=timedelta(seconds=5),
    maximum_attempts=3,
    non_retryable_error_types=["PermanentMissionError"],
)


@workflow.defn(name="ResearchMissionV1")
class ResearchMissionWorkflow:
    @workflow.run
    async def run(self, args: dict[str, str | int]) -> str:
        owner, mission = str(args["owner"]), str(args["mission"])

        async def call(name: str, index: int = -1) -> str:
            result = await workflow.execute_activity(
                name,
                args=[owner, mission, index],
                result_type=str,
                start_to_close_timeout=timedelta(seconds=270),
                heartbeat_timeout=timedelta(seconds=15),
                retry_policy=RETRY,
                cancellation_type=workflow.ActivityCancellationType.TRY_CANCEL,
            )

            return cast(str, result)

        async def execute() -> str:
            await call("mission_created")
            await call("personal_search")
            queries = int(await call("gap_detection"))
            for i in range(queries):
                await call("public_search", i)
            sources = int(await call("select_sources"))

            async def source(i: int) -> None:
                await call("fetch_sources", i)
                await call("process_sources", i)

            concurrency = int(args.get("concurrency", 5))
            for start in range(0, sources, concurrency):
                await asyncio.gather(
                    *(source(i) for i in range(start, min(sources, start + concurrency)))
                )
            await call("freeze_evidence")
            await call("detect_conflicts")
            await call("synthesize")
            await call("extract_actions")
            return await call("publish")

        try:
            return await asyncio.wait_for(execute(), timeout=int(args["deadline"]))
        except (asyncio.CancelledError, CancelledError):
            await asyncio.shield(call("cancel"))
            raise
        except (ActivityError, TimeoutError):
            await call("fail")
            raise
