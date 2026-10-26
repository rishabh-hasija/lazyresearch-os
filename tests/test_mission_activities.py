import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from lazyresearch.application.mission_models import MissionError
from lazyresearch.infrastructure.workflows.runtime import activities


@pytest.mark.parametrize(
    "error, code",
    [
        (MissionError("NO_EVIDENCE"), "NO_EVIDENCE"),
        (MissionError("PRIVATE source content"), "UNCLASSIFIED"),
        (RuntimeError("PRIVATE credential"), "UNCLASSIFIED"),
    ],
)
def test_activity_logs_rejected_operation_without_leaking_exception_contents(caplog, error, code):
    def reject(*args):
        raise error

    ops = SimpleNamespace(freeze_evidence=reject)
    activity = next(
        a for a in activities(ops) if a.__temporal_activity_definition.name == "freeze_evidence"
    )

    async def run():
        with pytest.raises(ApplicationError) as caught:
            await ActivityEnvironment().run(activity, str(uuid4()), str(uuid4()), -1)
        assert caught.value.non_retryable
        assert caught.value.message in {"INVALID_OPERATION", "OPERATION_FAILED"}
        assert "PRIVATE" not in str(caught.value)

    asyncio.run(run())
    assert "activity=freeze_evidence" in caplog.text and f"code={code}" in caplog.text
    assert "reject" in caplog.text and "PRIVATE" not in caplog.text
