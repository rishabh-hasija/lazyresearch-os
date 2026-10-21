"""Explicit local Temporal integration; deterministic business tests need no runtime."""

import asyncio
import os
from uuid import uuid4

import pytest
from temporalio.client import Client
from temporalio.worker import Replayer

from lazyresearch.application.mission_models import MissionScope
from lazyresearch.infrastructure.workflows.research import ResearchMissionWorkflow
from lazyresearch.infrastructure.workflows.runtime import reconcile, research_worker
from tests.integration.test_missions import mission_setup  # noqa: F401, F811

pytestmark = pytest.mark.integration


def test_real_workflow_publication_replay_and_dispatch_retry(mission_setup):  # noqa: F811
    address = os.environ.get("TEMPORAL_TEST_ADDRESS")
    if not address:
        pytest.skip("TEMPORAL_TEST_ADDRESS not configured")
    ops, owner, topic, *_ = mission_setup
    mission = ops.store.create_mission(
        owner, topic.id, "Battery", MissionScope(public=True, require_current=True)
    )

    async def run():
        client = await Client.connect(address)
        queue = "lr-test-" + uuid4().hex
        async with research_worker(client, ops, queue):
            assert await reconcile(client, ops.store, queue) == 1
            # Reconcile an ambiguous dispatch acknowledgment: duplicate start must be harmless.
            with ops.store.transaction() as s:
                from lazyresearch.infrastructure.persistence.mission_models import MissionRow

                s.get(MissionRow, mission.id).dispatched = False
            await reconcile(client, ops.store, queue)
            handle = client.get_workflow_handle(str(mission.id))
            result = await asyncio.wait_for(handle.result(), 60)
            history = await handle.fetch_history()
        await Replayer(workflows=[ResearchMissionWorkflow]).replay_workflow(history)
        assert ops.store.get_topic(owner, topic.id).current_result_id == uuid_from(result)
        assert len(ops.store.versions(owner, topic.id)) == 1
        # No evidence follows the actual durable failure path and preserves Current Brief.
        empty = ops.store.create_mission(owner, topic.id, "Battery", MissionScope(personal=False))
        async with research_worker(client, ops, queue):
            await reconcile(client, ops.store, queue)
            from temporalio.client import WorkflowFailureError

            with pytest.raises(WorkflowFailureError):
                await client.get_workflow_handle(str(empty.id)).result()
        assert ops.store.get_mission(owner, empty.id).status.value == "FAILED"
        assert len(ops.store.versions(owner, topic.id)) == 1

    asyncio.run(run())


def uuid_from(value):
    from uuid import UUID

    return UUID(value)


def test_activity_retry_worker_restart_and_cancellation(mission_setup):  # noqa: F811
    from threading import Event

    from lazyresearch.application.mission_models import TransientMissionError
    from lazyresearch.infrastructure.workflows.runtime import cancel_mission

    address = os.environ.get("TEMPORAL_TEST_ADDRESS")
    if not address:
        pytest.skip("TEMPORAL_TEST_ADDRESS not configured")
    ops, owner, topic, pages, search, synthesis = mission_setup
    attempted = Event()
    original_search = search.search
    calls = []

    def retry_once(query, limit):
        calls.append(query)
        if len(calls) == 1:
            attempted.set()
            raise TransientMissionError("SEARCH_UNAVAILABLE")
        return original_search(query, limit)

    search.search = retry_once
    first = ops.store.create_mission(
        owner, topic.id, "Battery", MissionScope(public=True, require_current=True)
    )

    async def run():
        client = await Client.connect(address)
        queue = "lr-restart-" + uuid4().hex
        async with research_worker(client, ops, queue):
            await reconcile(client, ops.store, queue)
            assert await asyncio.to_thread(attempted.wait, 15)
        async with research_worker(client, ops, queue):
            handle = client.get_workflow_handle(str(first.id))
            await asyncio.wait_for(handle.result(), 60)
        assert len(calls) == 2
        assert len(pages.calls) == 2
        entered, release = Event(), Event()
        original_synthesize = synthesis.synthesize

        def waiting(request):
            entered.set()
            assert release.wait(30)
            return original_synthesize(request)

        synthesis.synthesize = waiting
        second = ops.store.create_mission(owner, topic.id, "Battery", MissionScope())
        async with research_worker(client, ops, queue):
            await reconcile(client, ops.store, queue)
            assert await asyncio.to_thread(entered.wait, 15)
            await cancel_mission(client, ops.store, owner, second.id)
            release.set()
            from temporalio.client import WorkflowFailureError

            with pytest.raises(WorkflowFailureError):
                await client.get_workflow_handle(str(second.id)).result()
        assert ops.store.get_mission(owner, second.id).status.value == "CANCELLED"
        assert len(ops.store.versions(owner, topic.id)) == 1

    asyncio.run(run())


def test_source_retry_and_publish_ack_loss_do_not_duplicate(mission_setup):  # noqa: F811
    from collections import Counter

    from lazyresearch.application.intake_models import ErrorCode, SourceError
    from lazyresearch.application.mission_models import TransientMissionError

    address = os.environ.get("TEMPORAL_TEST_ADDRESS")
    if not address:
        pytest.skip("TEMPORAL_TEST_ADDRESS not configured")
    ops, owner, topic, pages, search, _ = mission_setup
    calls = Counter()
    fetch = pages.fetch

    def flaky(url):
        calls[url] += 1
        if url == search.urls[0] and calls[url] == 1:
            raise SourceError(ErrorCode.FETCH_TIMEOUT)
        return fetch(url)

    pages.fetch = flaky
    published = []
    publish = ops.store.publish

    def lost_ack(owner_id, mission_id):
        result = publish(owner_id, mission_id)
        published.append(result)
        if len(published) == 1:
            raise TransientMissionError("SIMULATED_ACK_LOSS")
        return result

    ops.store.publish = lost_ack
    mission = ops.store.create_mission(
        owner, topic.id, "Battery", MissionScope(public=True, require_current=True)
    )

    async def run():
        client = await Client.connect(address)
        queue = "lr-idempotency-" + uuid4().hex
        async with research_worker(client, ops, queue):
            await reconcile(client, ops.store, queue)
            await asyncio.wait_for(client.get_workflow_handle(str(mission.id)).result(), 60)

    asyncio.run(run())
    assert calls[search.urls[0]] == 2 and calls[search.urls[1]] == 1
    assert len(published) == 2 and published[0] == published[1]
    assert len(ops.store.versions(owner, topic.id)) == 1
