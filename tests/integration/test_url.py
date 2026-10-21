from uuid import uuid4

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from lazyresearch.application.intake import IntakeService
from lazyresearch.application.intake_models import ErrorCode, IntakeInput
from lazyresearch.domain.content import SourceType
from lazyresearch.domain.identity import OwnerId
from lazyresearch.infrastructure.persistence.models import CaptureRow, ContentRow
from lazyresearch.infrastructure.persistence.repositories import (
    SQLAlchemyIntakeStore,
    SQLAlchemyProcessingRepository,
)
from lazyresearch.infrastructure.sources.extract import SourceTextExtractor

pytestmark = pytest.mark.integration


def test_url_unchanged_changed_and_signed_query_identity(
    db: Engine,
    store: SQLAlchemyIntakeStore,
    jobs: SQLAlchemyProcessingRepository,
    controlled_fetcher,
    server,
) -> None:
    service = IntakeService(store, jobs, controlled_fetcher, SourceTextExtractor())
    owner = OwnerId(uuid4())
    url = f"http://public.test:{server.server_port}/page?edition=1&signature=synthetic"
    entry = IntakeInput(source_type=SourceType.URL, url=url)
    original_payload = server.payload
    try:
        server.payload = b"saved first"
        first = service.ingest(owner, "first", (entry,))
        repeat = service.ingest(owner, "same", (entry,))
        assert first.saved == 1 and repeat.duplicate == 1
        assert first.entries[0].content_id == repeat.entries[0].content_id
        server.payload = b"updated page"
        changed = service.ingest(owner, "changed", (entry,))
        old_id, new_id = first.entries[0].content_id, changed.entries[0].content_id
        assert old_id is not None and new_id is not None and old_id != new_id
        old, _ = store.original(owner, old_id)
        new, _ = store.original(owner, new_id)
        assert old.raw_content == b"saved first"
        assert new.predecessor_id == old_id and new.raw_content == b"updated page"
        assert new.original_url == new.canonical_url == url
        # Reverting to known bytes reuses that snapshot but records the latest capture.
        server.payload = b"saved first"
        reverted = service.ingest(owner, "reverted", (entry,))
        assert reverted.duplicate == 1 and reverted.entries[0].content_id == old_id
        server.payload = b"third page"
        third = service.ingest(owner, "third", (entry,))
        assert store.original(owner, third.entries[0].content_id)[0].predecessor_id == old_id
        other_url = url.replace("edition=1", "edition=2")
        other = service.ingest(
            owner, "other", (IntakeInput(source_type=SourceType.URL, url=other_url),)
        )
        assert other.saved == 1 and other.entries[0].content_id != new_id
        with Session(db) as s:
            assert s.scalar(select(func.count()).select_from(ContentRow)) == 4
            assert s.scalar(select(func.count()).select_from(CaptureRow)) == 6
            row = s.get(ContentRow, new_id)
            assert row.http_status == 200 and row.content_type == "text/plain"
    finally:
        server.payload = original_payload


def test_redirect_preserves_submitted_and_final_urls(
    store: SQLAlchemyIntakeStore,
    jobs: SQLAlchemyProcessingRepository,
    controlled_fetcher,
    server,
) -> None:
    service = IntakeService(store, jobs, controlled_fetcher, SourceTextExtractor())
    owner = OwnerId(uuid4())
    url = f"http://public.test:{server.server_port}/redirect"
    result = service.ingest(owner, "redirect", (IntakeInput(source_type=SourceType.URL, url=url),))
    snapshot, _ = store.original(owner, result.entries[0].content_id)
    assert snapshot.original_url == url
    assert snapshot.canonical_url.endswith("/ok?keep=signed")


def test_url_failure_does_not_rollback_saved_sibling(
    store: SQLAlchemyIntakeStore,
    jobs: SQLAlchemyProcessingRepository,
    controlled_fetcher,
    server,
) -> None:
    service = IntakeService(store, jobs, controlled_fetcher, SourceTextExtractor())
    result = service.ingest(
        OwnerId(uuid4()),
        "mixed",
        (
            IntakeInput(
                source_type=SourceType.URL, url=f"http://public.test:{server.server_port}/ok"
            ),
            IntakeInput(
                source_type=SourceType.URL, url=f"http://public.test:{server.server_port}/private"
            ),
            IntakeInput(
                source_type=SourceType.URL, url=f"http://public.test:{server.server_port}/missing"
            ),
        ),
    )
    assert result.saved == 1 and result.failed == 2
    assert result.entries[1].error_code is ErrorCode.PRIVATE_NETWORK_BLOCKED
    assert result.entries[2].http_status == 404
