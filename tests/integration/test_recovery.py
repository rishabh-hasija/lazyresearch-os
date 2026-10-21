from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import Engine, event, func, select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from lazyresearch.application.intake import IntakeService
from lazyresearch.application.intake_models import FetchedSource, IntakeInput
from lazyresearch.domain.content import SourceType
from lazyresearch.domain.identity import OwnerId
from lazyresearch.infrastructure.persistence.models import CaptureRow, ContentRow, EntryRow, JobRow
from lazyresearch.infrastructure.persistence.repositories import (
    SQLAlchemyIntakeStore,
    SQLAlchemyProcessingRepository,
)
from lazyresearch.infrastructure.sources.extract import SourceTextExtractor
from lazyresearch.ports.errors import RepositoryConflict, RepositoryError

pytestmark = pytest.mark.integration


def prepared(store: SQLAlchemyIntakeStore):
    owner = OwnerId(uuid4())
    batch = store.create_batch(
        owner, "crash", (IntakeInput(source_type=SourceType.TEXT, payload=b"saved"),)
    )
    lease = store.claim_entry(owner, store.batch(owner, batch).entries[0].id)
    assert lease is not None
    source = FetchedSource(
        payload=b"saved",
        final_url="",
        fetched_at=datetime.now(UTC),
        http_status=0,
        content_type="text/plain",
    )
    return owner, batch, lease, source


def test_original_capture_and_pending_job_rollback_together(
    db: Engine,
    store: SQLAlchemyIntakeStore,
    service: IntakeService,
) -> None:
    owner, batch, lease, source = prepared(store)

    def fail(*args):
        raise SQLAlchemyError("synthetic database failure, no user payload")

    event.listen(CaptureRow, "before_insert", fail)
    try:
        with pytest.raises(RepositoryError):
            store.save_original(lease, source)
    finally:
        event.remove(CaptureRow, "before_insert", fail)
    with Session(db) as s:
        for model in (ContentRow, CaptureRow, JobRow):
            assert s.scalar(select(func.count()).select_from(model)) == 0
    with db.begin() as c:
        c.execute(
            update(EntryRow)
            .where(EntryRow.id == lease.entry_id)
            .values(lease_until=func.clock_timestamp() - text("interval '1 second'"))
        )
    result = service.resume(owner, batch)
    assert result.saved == 1


def test_expired_extractor_cannot_publish_after_reclaim(
    db: Engine,
    store: SQLAlchemyIntakeStore,
    jobs: SQLAlchemyProcessingRepository,
) -> None:
    owner, _, entry, source = prepared(store)
    content_id = store.save_original(entry, source)
    old = jobs.claim(owner, "EXTRACT", content_id=content_id)
    assert old is not None
    with db.begin() as c:
        c.execute(
            update(JobRow)
            .where(JobRow.id == old.id)
            .values(lease_until=func.clock_timestamp() - text("interval '1 second'"))
        )
    new = jobs.claim(owner, "EXTRACT", content_id=content_id)
    assert new is not None
    data = SourceTextExtractor().extract(b"saved", SourceType.TEXT, "text/plain")
    with pytest.raises(RepositoryConflict):
        store.save_extraction(old, data)
    assert store.extraction(owner, content_id) is None
    store.save_extraction(new, data)
    assert store.extraction(owner, content_id).data.text == "saved"


def test_same_request_concurrently_creates_one_batch_and_capture(
    db: Engine,
    service: IntakeService,
) -> None:
    owner, barrier = OwnerId(uuid4()), Barrier(2)
    entry = IntakeInput(source_type=SourceType.TEXT, payload=b"same request")

    def ingest(_):
        barrier.wait(timeout=10)
        return service.ingest(owner, "same-key", (entry,))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(ingest, range(2)))
    assert results[0].batch_id == results[1].batch_id
    with Session(db) as s:
        assert s.scalar(select(func.count()).select_from(ContentRow)) == 1
        assert s.scalar(select(func.count()).select_from(CaptureRow)) == 1


def test_lease_cannot_substitute_other_input_or_local_bytes(store: SQLAlchemyIntakeStore) -> None:
    _, _, lease, source = prepared(store)
    with pytest.raises(RepositoryConflict, match="inputs differ"):
        store.save_original(replace(lease, input=replace(lease.input, payload=b"tampered")), source)
    with pytest.raises(RepositoryConflict, match="submitted bytes"):
        store.save_original(lease, replace(source, payload=b"tampered"))


def test_parser_observes_already_committed_original(
    db: Engine,
    service: IntakeService,
) -> None:
    class CommitCheckingExtractor(SourceTextExtractor):
        def extract(self, payload, source_type, content_type):
            with Session(db) as independent:
                assert independent.scalar(select(func.count()).select_from(ContentRow)) == 1
                assert independent.scalar(select(func.count()).select_from(CaptureRow)) == 1
            return super().extract(payload, source_type, content_type)

    service.extractor = CommitCheckingExtractor()
    result = service.ingest(
        OwnerId(uuid4()),
        "commit-first",
        (IntakeInput(source_type=SourceType.TEXT, payload=b"original"),),
    )
    assert result.saved == 1 and result.extraction_pending == 0
