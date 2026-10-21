"""Activity bindings, explicit worker startup and dispatch reconciliation."""

import asyncio
from collections.abc import Callable, Coroutine
from datetime import timedelta
from typing import Any
from uuid import UUID

from temporalio import activity
from temporalio.client import Client, WorkflowExecutionStatus
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import ApplicationError, WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode
from temporalio.worker import Worker

from lazyresearch.application.mission_models import MissionError, TransientMissionError
from lazyresearch.application.missions import ResearchOperations
from lazyresearch.infrastructure.persistence.missions import PostgreSQLMissionStore
from lazyresearch.infrastructure.workflows.research import ResearchMissionWorkflow
from lazyresearch.ports.errors import RepositoryError


def activities(operations: ResearchOperations) -> list[Callable[..., Coroutine[Any, Any, str]]]:
    def binding(name: str) -> Callable[..., Coroutine[Any, Any, str]]:
        @activity.defn(name=name)
        async def invoke(owner_text: str, mission_text: str, index: int) -> str:
            owner, mission = UUID(owner_text), UUID(mission_text)
            activity_attempt = activity.info().attempt
            final_attempt = activity_attempt >= 3

            def perform() -> str:
                match name:
                    case "mission_created":
                        operations.store.start(owner, mission)
                    case "personal_search":
                        operations.personal_search(owner, mission)
                    case "gap_detection":
                        return str(operations.gap_detection(owner, mission))
                    case "public_search":
                        operations.public_search(owner, mission, index, final_attempt=final_attempt)
                    case "select_sources":
                        return str(operations.select_sources(owner, mission))
                    case "fetch_sources":
                        operations.fetch_source(
                            owner,
                            mission,
                            index,
                            final_attempt=final_attempt,
                            retry_attempt=activity_attempt > 1,
                        )
                    case "process_sources":
                        operations.process_source(owner, mission, index)
                    case "freeze_evidence":
                        operations.freeze_evidence(owner, mission)
                    case "detect_conflicts":
                        operations.detect_contradictions(owner, mission)
                    case "synthesize":
                        operations.synthesize(owner, mission)
                    case "extract_actions":
                        operations.validate(owner, mission)
                    case "publish":
                        return str(operations.store.publish(owner, mission))
                    case "cancel":
                        operations.store.terminal(owner, mission, "CANCELLED", "CANCELLED")
                    case "fail":
                        operations.store.terminal(owner, mission, "FAILED", "WORKFLOW_FAILED")
                    case _:
                        raise MissionError("UNKNOWN_STAGE")
                return "ok"

            task = asyncio.create_task(asyncio.to_thread(perform))
            try:
                while not task.done():
                    activity.heartbeat()
                    await asyncio.wait({task}, timeout=3)
                return await task
            except (TransientMissionError, RepositoryError):
                raise ApplicationError(
                    "TRANSIENT_OPERATION", type="TransientMissionError"
                ) from None
            except MissionError:
                raise ApplicationError(
                    "INVALID_OPERATION", type="PermanentMissionError", non_retryable=True
                ) from None
            except Exception:
                # Provider/schema/DB exception text may contain payloads. Never put it in history.
                raise ApplicationError(
                    "OPERATION_FAILED", type="PermanentMissionError", non_retryable=True
                ) from None

        return invoke

    return [
        binding(name)
        for name in (
            "mission_created",
            "personal_search",
            "gap_detection",
            "public_search",
            "select_sources",
            "fetch_sources",
            "process_sources",
            "freeze_evidence",
            "detect_conflicts",
            "synthesize",
            "extract_actions",
            "publish",
            "cancel",
            "fail",
        )
    ]


async def reconcile(client: Client, store: PostgreSQLMissionStore, task_queue: str) -> int:
    for owner, mission in await asyncio.to_thread(store.active_dispatches):
        try:
            description = await client.get_workflow_handle(str(mission)).describe()
        except RPCError as exc:
            if exc.status != RPCStatusCode.NOT_FOUND:
                raise
            await asyncio.to_thread(store.reset_dispatch, owner, mission)
            continue
        if description.status in {
            WorkflowExecutionStatus.FAILED,
            WorkflowExecutionStatus.TIMED_OUT,
            WorkflowExecutionStatus.TERMINATED,
            WorkflowExecutionStatus.CANCELED,
        }:
            state = (
                "CANCELLED" if description.status == WorkflowExecutionStatus.CANCELED else "FAILED"
            )
            await asyncio.to_thread(store.terminal, owner, mission, state, "WORKFLOW_TERMINAL")
    count = 0
    for owner, mission, deadline in await asyncio.to_thread(store.pending_dispatches):
        scope = await asyncio.to_thread(store.scope, owner, mission)
        try:
            await client.start_workflow(
                "ResearchMissionV1",
                {
                    "owner": str(owner),
                    "mission": str(mission),
                    "deadline": deadline,
                    "concurrency": scope.fetch_concurrency,
                },
                id=str(mission),
                task_queue=task_queue,
                execution_timeout=timedelta(seconds=deadline + 300),
                id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
            )
        except WorkflowAlreadyStartedError:
            pass
        await asyncio.to_thread(store.mark_dispatched, owner, mission)
        count += 1
    return count


def research_worker(client: Client, operations: ResearchOperations, task_queue: str) -> Worker:
    return Worker(
        client,
        task_queue=task_queue,
        workflows=[ResearchMissionWorkflow],
        activities=activities(operations),
        max_concurrent_activities=5,
    )


async def cancel_mission(
    client: Client, store: PostgreSQLMissionStore, owner: UUID, mission: UUID
) -> None:
    # Database fence first; a late inference or activity completion cannot publish afterward.
    await asyncio.to_thread(store.terminal, owner, mission, "CANCELLED", "CANCELLED")
    await client.get_workflow_handle(str(mission)).cancel()
