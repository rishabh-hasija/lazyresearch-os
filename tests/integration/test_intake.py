from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, func, inspect, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from lazyresearch.application.intake import IntakeService
from lazyresearch.application.intake_models import (
    ErrorCode,
    ExtractionStatus,
    FetchedSource,
    IntakeInput,
)
from lazyresearch.domain.content import CaptureOccurrence, ContentItem, SourceType
from lazyresearch.domain.identity import CaptureId, ContentId, OwnerId
from lazyresearch.infrastructure.persistence.models import (
    CaptureRow,
    ContentRow,
    EntryRow,
    ExtractionRow,
    JobRow,
)
from lazyresearch.infrastructure.persistence.repositories import (
    SQLAlchemyContentRepository,
    SQLAlchemyIntakeStore,
    SQLAlchemyProcessingRepository,
)
from lazyresearch.infrastructure.sources.extract import SourceTextExtractor
from lazyresearch.ports.errors import RepositoryConflict

pytestmark = pytest.mark.integration


def pasted(raw: bytes = b"Original\r\ntext") -> IntakeInput:
    return IntakeInput(source_type=SourceType.TEXT, payload=raw)


def count(db: Engine, model: type) -> int:
    with Session(db) as s:
        return s.scalar(select(func.count()).select_from(model))


def test_migration_schema_downgrade_and_upgrade(db: Engine) -> None:
    expected = {
        "owner_scope",
        "intake_batch",
        "intake_entry",
        "content_item",
        "capture_occurrence",
        "content_extraction",
        "processing_job",
        "alembic_version",
        "processing_run",
        "content_analysis",
        "action_proposal",
        "analysis_evidence",
        "retrieval_state",
        "content_chunk",
        "collection",
        "collection_membership",
        "content_embedding",
        "research_topic",
        "research_mission",
        "research_stage",
        "research_evidence",
        "research_result",
        "research_proposal",
        "ranking_observation",
        "user_interaction",
    }
    if "embedding_vector" in inspect(db).get_table_names():
        expected.add("embedding_vector")
    assert set(inspect(db).get_table_names()) == expected
    config = Config("alembic.ini")
    with db.begin() as c:
        config.attributes["connection"] = c
        command.downgrade(config, "base")
        command.upgrade(config, "head")
    assert set(inspect(db).get_table_names()) == expected


def test_pasted_text_preserves_raw_and_separate_extraction(
    db: Engine,
    service: IntakeService,
    store: SQLAlchemyIntakeStore,
) -> None:
    owner = OwnerId(uuid4())
    result = service.ingest(owner, "first", (pasted(),))
    assert (result.total, result.saved, result.failed, result.duplicate) == (1, 1, 0, 0)
    content_id = result.entries[0].content_id
    assert content_id is not None
    snapshot, _ = store.original(owner, content_id)
    assert isinstance(snapshot, ContentItem)
    assert snapshot.raw_content == b"Original\r\ntext"
    extraction = store.extraction(owner, content_id)
    assert extraction is not None
    assert extraction.data.text == "Original\ntext"
    assert snapshot.raw_content_hash != extraction.data.normalized_hash
    fresh = SQLAlchemyProcessingRepository(db)
    lease = fresh.claim(owner, "ANALYZE")
    assert lease is not None and lease.content_id == content_id
    assert lease.extraction_id == extraction.id


@pytest.mark.parametrize(
    "entry",
    [
        IntakeInput(
            source_type=SourceType.TEXT,
            payload=b"file",
            filename="a.txt",
            content_type="text/plain",
        ),
        IntakeInput(source_type=SourceType.MARKDOWN, payload=b"# Heading\r\nText", filename="a.md"),
    ],
)
def test_text_file_and_markdown(service: IntakeService, entry: IntakeInput) -> None:
    result = service.ingest(OwnerId(uuid4()), "files", (entry,))
    assert result.saved == 1
    assert result.entries[0].extraction_status is ExtractionStatus.SUCCEEDED


def test_mixed_batch_isolation_and_summary(service: IntakeService) -> None:
    result = service.ingest(
        OwnerId(uuid4()),
        "mixed",
        (
            pasted(),
            IntakeInput(source_type=SourceType.URL, url="file:///etc/passwd"),
            IntakeInput(source_type=SourceType.TEXT, payload=b"hello", filename="a.exe"),
            IntakeInput(source_type=SourceType.MARKDOWN, payload=b"# Good", filename="a.md"),
        ),
    )
    assert (result.total, result.saved, result.failed, result.pending) == (4, 2, 2, 0)
    assert result.entries[1].error_code is ErrorCode.UNSUPPORTED_SCHEME
    assert result.entries[2].error_code is ErrorCode.UNSUPPORTED_FILE


@pytest.mark.parametrize(
    "entry", [pasted(), IntakeInput(source_type=SourceType.TEXT, payload=b"file", filename="a.txt")]
)
def test_duplicates_keep_two_capture_occurrences(
    db: Engine, service: IntakeService, entry: IntakeInput
) -> None:
    owner = OwnerId(uuid4())
    one = service.ingest(owner, "first", (entry,))
    two = service.ingest(owner, "second", (entry,))
    assert one.saved == 1 and two.duplicate == 1
    assert one.entries[0].content_id == two.entries[0].content_id
    assert count(db, ContentRow) == 1
    assert count(db, CaptureRow) == 2
    assert count(db, ExtractionRow) == 1
    assert count(db, JobRow) == 2  # One finished extraction, one pending analysis.


def test_same_request_retry_is_idempotent_and_changed_input_conflicts(
    db: Engine, service: IntakeService
) -> None:
    owner = OwnerId(uuid4())
    one = service.ingest(owner, "retry", (pasted(),))
    two = service.ingest(owner, "retry", (pasted(),))
    assert one == two
    assert count(db, CaptureRow) == 1
    with pytest.raises(RepositoryConflict):
        service.ingest(owner, "retry", (pasted(b"different"),))


def test_no_cross_owner_deduplication_or_lookup(
    db: Engine, service: IntakeService, store: SQLAlchemyIntakeStore
) -> None:
    owner1, owner2 = OwnerId(uuid4()), OwnerId(uuid4())
    a = service.ingest(owner1, "a", (pasted(),))
    b = service.ingest(owner2, "b", (pasted(),))
    assert a.entries[0].content_id != b.entries[0].content_id
    assert count(db, ContentRow) == 2
    assert SQLAlchemyContentRepository(db).get(owner2, a.entries[0].content_id) is None
    with pytest.raises(RepositoryConflict):
        store.batch(owner2, a.batch_id)
    assert store.extraction(owner2, a.entries[0].content_id) is None


def test_failed_decode_keeps_original_and_no_analysis_job(
    db: Engine, service: IntakeService
) -> None:
    result = service.ingest(OwnerId(uuid4()), "invalid-text", (pasted(b"\xff\x00\x80"),))
    assert result.saved == 1 and result.failed == 0 and result.extraction_failed == 1
    assert result.entries[0].error_code is ErrorCode.DECODE_FAILED
    assert count(db, ContentRow) == 1 and count(db, JobRow) == 1


def test_oversize_rejected_without_source_storage(db: Engine, service: IntakeService) -> None:
    service.limits = replace(service.limits, max_upload_bytes=4)
    result = service.ingest(OwnerId(uuid4()), "large", (pasted(b"12345"), pasted(b"ok")))
    assert result.failed == 1 and result.saved == 1
    assert result.entries[0].error_code is ErrorCode.FILE_TOO_LARGE
    assert count(db, ContentRow) == 1


def test_crash_after_original_commit_recovers_extraction(
    db: Engine,
    store: SQLAlchemyIntakeStore,
    service: IntakeService,
) -> None:
    owner = OwnerId(uuid4())
    batch = store.create_batch(owner, "crash", (pasted(),))
    receipt = store.batch(owner, batch).entries[0]
    lease = store.claim_entry(owner, receipt.id)
    assert lease is not None
    content_id = store.save_original(
        lease,
        FetchedSource(
            payload=b"Original\r\ntext",
            final_url="",
            fetched_at=datetime.now(UTC),
            http_status=0,
            content_type="text/plain",
        ),
    )
    assert store.batch(owner, batch).extraction_pending == 1
    assert count(db, ContentRow) == 1 and count(db, JobRow) == 1
    # New repository instance, then normal application restart/resume.
    assert (
        SQLAlchemyIntakeStore(db, extraction_version=SourceTextExtractor.version)
        .original(owner, content_id)[0]
        .raw_content
    )
    result = service.resume(owner, batch)
    assert result.saved == 1 and result.extraction_pending == 0
    assert count(db, CaptureRow) == 1


def test_expired_entry_lease_is_reclaimed_and_stale_write_rejected(
    db: Engine,
    store: SQLAlchemyIntakeStore,
    service: IntakeService,
) -> None:
    owner = OwnerId(uuid4())
    batch = store.create_batch(owner, "lease", (pasted(),))
    entry = store.batch(owner, batch).entries[0]
    old = store.claim_entry(owner, entry.id)
    assert old is not None
    assert store.claim_entry(owner, entry.id) is None
    with db.begin() as c:
        c.execute(
            update(EntryRow)
            .where(EntryRow.id == entry.id)
            .values(lease_until=func.clock_timestamp() - text("interval '1 second'"))
        )
    new = store.claim_entry(owner, entry.id)
    assert new is not None and new.token != old.token
    with pytest.raises(RepositoryConflict):
        store.fail_entry(old, ErrorCode.FETCH_FAILED)


def test_concurrent_identical_submissions(db: Engine, service: IntakeService) -> None:
    owner, barrier = OwnerId(uuid4()), Barrier(2)

    def ingest(key: str):
        barrier.wait(timeout=10)
        return service.ingest(owner, key, (pasted(),))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(ingest, ["race-a", "race-b"]))
    assert sum(r.saved for r in results) == 1
    assert sum(r.duplicate for r in results) == 1
    assert count(db, ContentRow) == 1 and count(db, CaptureRow) == 2
    assert count(db, JobRow) == 2


def test_pending_claim_expiry_fencing_and_finished_job(
    db: Engine,
    service: IntakeService,
    jobs: SQLAlchemyProcessingRepository,
) -> None:
    owner = OwnerId(uuid4())
    service.ingest(owner, "jobs", (pasted(),))
    old = jobs.claim(owner, "ANALYZE")
    assert old is not None
    assert jobs.claim(owner, "ANALYZE") is None
    with db.begin() as c:
        c.execute(
            update(JobRow)
            .where(JobRow.id == old.id)
            .values(lease_until=func.clock_timestamp() - text("interval '1 second'"))
        )
    new = SQLAlchemyProcessingRepository(db).claim(owner, "ANALYZE")
    assert new is not None and new.id == old.id and new.token != old.token
    with pytest.raises(RepositoryConflict):
        jobs.finish(old)
    jobs.finish(new)
    assert jobs.claim(owner, "ANALYZE") is None


def test_concurrent_workers_cannot_share_active_lease(
    service: IntakeService,
    jobs: SQLAlchemyProcessingRepository,
) -> None:
    owner, barrier = OwnerId(uuid4()), Barrier(2)
    service.ingest(owner, "jobs", (pasted(),))

    def claim(_):
        barrier.wait(timeout=10)
        return jobs.claim(owner, "ANALYZE")

    with ThreadPoolExecutor(max_workers=2) as pool:
        leases = list(pool.map(claim, range(2)))
    assert sum(lease is not None for lease in leases) == 1


def test_repository_roundtrip_idempotency_and_immutable_conflicts(db: Engine) -> None:
    owner = OwnerId(uuid4())
    snapshot = ContentItem(
        id=ContentId(uuid4()),
        owner_id=owner,
        source_type=SourceType.TEXT,
        captured_at=datetime.now(UTC),
        raw_content=b"note",
        raw_content_hash=sha256(b"note").hexdigest(),
    )
    capture = CaptureOccurrence(
        id=CaptureId(uuid4()),
        owner_id=owner,
        content_id=snapshot.id,
        captured_at=snapshot.captured_at,
        intake_reference="standalone",
    )
    repo = SQLAlchemyContentRepository(db)
    repo.save_capture(owner, snapshot, capture)
    repo.save_capture(owner, snapshot, capture)
    assert repo.get(owner, snapshot.id) == snapshot
    assert count(db, CaptureRow) == 1
    with pytest.raises(RepositoryConflict):
        repo.save_capture(owner, replace(snapshot, original_title="overwrite"), capture)
    with pytest.raises(RepositoryConflict):
        repo.save_capture(OwnerId(uuid4()), snapshot, capture)
    with pytest.raises(DBAPIError), db.begin() as c:
        c.execute(
            update(ContentRow)
            .where(ContentRow.id == snapshot.id)
            .values(original_title="overwrite")
        )
