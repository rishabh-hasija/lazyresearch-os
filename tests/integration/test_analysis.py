from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import event, inspect, select, text, update
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.orm import Session

from lazyresearch.application.analysis import ProcessPendingContent, assemble, segments
from lazyresearch.application.analysis_models import AnalysisConfig, AnalysisRequest
from lazyresearch.application.intake_models import IntakeInput
from lazyresearch.domain.content import SourceType
from lazyresearch.domain.identity import OwnerId
from lazyresearch.infrastructure.ai.ollama import OllamaProcessor
from lazyresearch.infrastructure.persistence.analysis import SQLAlchemyAnalysisStore
from lazyresearch.infrastructure.persistence.models import (
    ActionProposalRow,
    AnalysisEvidenceRow,
    ContentAnalysisRow,
    JobRow,
    ProcessingRunRow,
)
from lazyresearch.ports.errors import RepositoryConflict, RepositoryError
from tests.analysis_helpers import FakeProcessor, FakeWire, parsed, payload

pytestmark = pytest.mark.integration


def saved(service, source="Submit by 2026-11-07."):
    owner = OwnerId(uuid4())
    result = service.ingest(
        owner, "analysis", (IntakeInput(source_type=SourceType.TEXT, payload=source.encode()),)
    )
    return owner, result.entries[0].content_id


def analysis_for(work, config):
    request = AnalysisRequest(
        work.lease.owner_id,
        work.lease.content_id,
        work.extraction.id,
        segments(work.extraction, config)[0],
        config,
    )
    return assemble(work, ((request, parsed(payload(request))),))


def rows(db, model):
    with Session(db) as s:
        return list(s.scalars(select(model)))


def expire(db, work):
    with db.begin() as c:
        c.execute(
            update(JobRow)
            .where(JobRow.id == work.lease.id)
            .values(lease_until=datetime.now(UTC) - timedelta(seconds=1))
        )


def test_analysis_atomic_success_original_proposals_and_metadata(db, service, store):
    owner, content = saved(service)
    original, _ = store.original(owner, content)
    config = AnalysisConfig(model_revision="actual-test-revision", provider_revision="test-runtime")
    analyses = SQLAlchemyAnalysisStore(db)
    fake = FakeProcessor()
    usecase = ProcessPendingContent(analyses, fake, config)
    result = usecase.process_one(owner)
    assert result.status == "SUCCEEDED"
    restored = analyses.get(owner, result.analysis_id)
    assert restored is not None and restored.processing == config.identity(
        store.extraction(owner, content).data.normalized_hash
    )
    assert restored.proposals[0].deadline.normalized.isoformat() == "2026-11-07"
    assert restored.claims[0].evidence[0].quote == "Submit by 2026-11-07."
    assert store.original(owner, content)[0] == original
    run = rows(db, ProcessingRunRow)[0]
    assert run.status == "SUCCEEDED" and run.attempt == 1 and run.error_code is None
    assert run.started_at <= run.ended_at and run.latency_seconds >= 0
    assert run.prompt_hash == config.prompt_hash and run.parameters == config.parameters
    assert run.calls[0]["outcome"] == "OK"
    assert len(rows(db, ActionProposalRow)) == 1 and len(rows(db, AnalysisEvidenceRow)) == 2
    assert usecase.process_one(owner).status == "IDLE"
    assert len(rows(db, ContentAnalysisRow)) == len(fake.requests) == 1
    assert analyses.get(OwnerId(uuid4()), result.analysis_id) is None


@pytest.mark.parametrize(
    "changes",
    [
        {"model": "alternate-model"},
        {"prompt_version": "new-prompt", "prompt": "Changed prompt"},
        {"schema_version": "analysis-v3"},
        {"pipeline_version": "new-pipeline"},
        {"temperature": 0.2},
        {"model_revision": "new-revision"},
    ],
)
def test_reprocessing_configuration_preserves_history(db, service, changes):
    owner, _ = saved(service)
    store = SQLAlchemyAnalysisStore(db)
    config = AnalysisConfig()
    first = ProcessPendingContent(store, FakeProcessor(), config).process_one(owner)
    original = store.get(owner, first.analysis_id)
    second = ProcessPendingContent(store, FakeProcessor(), replace(config, **changes)).process_one(
        owner
    )
    assert second.status == "SUCCEEDED" and first.analysis_id != second.analysis_id
    assert store.get(owner, first.analysis_id) == original
    assert store.get(owner, second.analysis_id).version != original.version
    assert len(rows(db, ContentAnalysisRow)) == 2


@pytest.mark.parametrize(
    "code", ["TIMEOUT", "UNAVAILABLE", "INVALID_RESPONSE", "INVALID_SCHEMA", "INVALID_LOCATOR"]
)
def test_failure_preserves_original_and_explicit_retry(db, service, store, code):
    owner, content = saved(service)
    analyses = SQLAlchemyAnalysisStore(db)
    config = AnalysisConfig()
    result = ProcessPendingContent(analyses, FakeProcessor(error=code), config).process_one(owner)
    assert result.status == "FAILED" and result.error_code == code
    assert store.original(owner, content)[0].raw_content == b"Submit by 2026-11-07."
    run = rows(db, ProcessingRunRow)[0]
    assert run.status == "FAILED" and run.error_code == code and run.calls[0]["outcome"] == code
    assert not rows(db, ContentAnalysisRow)
    assert (
        ProcessPendingContent(analyses, FakeProcessor(), config).process_one(owner).status == "IDLE"
    )
    analyses.retry_failed(owner, run.job_id)
    assert (
        ProcessPendingContent(analyses, FakeProcessor(), config).process_one(owner).status
        == "SUCCEEDED"
    )
    assert sorted(r.attempt for r in rows(db, ProcessingRunRow)) == [1, 2]


def test_expired_reclaimed_worker_cannot_publish_or_fail(db, service):
    owner, _ = saved(service)
    store, config = SQLAlchemyAnalysisStore(db), AnalysisConfig()
    first = store.claim(owner, config)
    expire(db, first)
    second = store.claim(owner, config)
    assert first.lease.id == second.lease.id and first.lease.token != second.lease.token
    with pytest.raises(RepositoryConflict):
        store.publish(first, analysis_for(first, config), ())
    with pytest.raises(RepositoryConflict):
        store.fail(first, "UNAVAILABLE", ())
    store.publish(second, analysis_for(second, config), ())
    assert sorted(r.status for r in rows(db, ProcessingRunRow)) == ["FAILED", "SUCCEEDED"]


@pytest.mark.parametrize("mode", ["cancel", "expire"])
def test_cancelled_or_expired_lease_cannot_publish_after_inference(db, service, mode):
    owner, _ = saved(service)
    store, config = SQLAlchemyAnalysisStore(db), AnalysisConfig()
    work = store.claim(owner, config)
    analysis = analysis_for(work, config)
    if mode == "cancel":
        store.cancel(owner, work.lease.id)
    else:
        expire(db, work)
    with pytest.raises(RepositoryConflict):
        store.publish(work, analysis, ())
    assert not rows(db, ContentAnalysisRow)


def test_db_failure_after_inference_rolls_back_all_outputs_and_recovers(db, service, store):
    owner, content = saved(service)
    analyses, config = SQLAlchemyAnalysisStore(db), AnalysisConfig()
    fake = FakeProcessor()

    def fail_proposal(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO action_proposal"):
            raise SQLAlchemyError("injected storage failure")

    event.listen(db, "before_cursor_execute", fail_proposal)
    try:
        with pytest.raises(RepositoryError):
            ProcessPendingContent(analyses, fake, config).process_one(owner)
    finally:
        event.remove(db, "before_cursor_execute", fail_proposal)
    assert len(fake.requests) == 1
    assert not rows(db, ContentAnalysisRow) and not rows(db, ActionProposalRow)
    assert rows(db, ProcessingRunRow)[0].status == "RUNNING"
    assert store.original(owner, content)[0].raw_content == b"Submit by 2026-11-07."
    with db.begin() as c:
        c.execute(
            update(JobRow)
            .where(JobRow.kind == "ANALYZE", JobRow.status == "RUNNING")
            .values(lease_until=datetime.now(UTC) - timedelta(seconds=1))
        )
    assert (
        ProcessPendingContent(analyses, FakeProcessor(), config).process_one(owner).status
        == "SUCCEEDED"
    )
    assert len(rows(db, ContentAnalysisRow)) == 1


def test_repair_audit_persisted(db, service):
    owner, _ = saved(service)
    wire = FakeWire(["not JSON"])
    outcome = ProcessPendingContent(
        SQLAlchemyAnalysisStore(db),
        OllamaProcessor("http://127.0.0.1:11434", wire=wire),
        AnalysisConfig(),
    ).process_one(owner)
    assert outcome.status == "SUCCEEDED"
    assert [c["outcome"] for c in rows(db, ProcessingRunRow)[0].calls] == ["INVALID_SCHEMA", "OK"]


def test_chunks_complete_and_partial_are_recorded(db, service):
    owner, _ = saved(service, "abcdefghijklmno")
    store = SQLAlchemyAnalysisStore(db)
    config = AnalysisConfig(max_input_chars=5, max_chunks=2)
    fake = FakeProcessor(action=False)
    outcome = ProcessPendingContent(store, fake, config).process_one(owner)
    analysis = store.get(owner, outcome.analysis_id)
    assert analysis.coverage == "PARTIAL" and analysis.covered_ranges == ((0, 5), (5, 10))
    assert len(fake.requests) == 2 and len(analysis.summaries) == 2
    full = ProcessPendingContent(
        store, FakeProcessor(action=False), replace(config, max_chunks=3)
    ).process_one(owner)
    assert store.get(owner, full.analysis_id).coverage == "COMPLETE"


def test_two_workers_claim_distinct_work(db, service):
    owner, _ = saved(service)
    service.ingest(
        owner, "second", (IntakeInput(source_type=SourceType.TEXT, payload=b"Another source."),)
    )
    barrier = Barrier(2)

    def claim():
        barrier.wait(timeout=10)
        return SQLAlchemyAnalysisStore(db).claim(owner, AnalysisConfig())

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(lambda _: claim(), range(2)))
    assert first.lease.id != second.lease.id


@pytest.mark.parametrize(
    "table", ["content_analysis", "action_proposal", "analysis_evidence", "processing_run"]
)
def test_successful_history_rejects_updates(db, service, table):
    owner, _ = saved(service)
    ProcessPendingContent(
        SQLAlchemyAnalysisStore(db), FakeProcessor(), AnalysisConfig()
    ).process_one(owner)
    with pytest.raises(DBAPIError), db.begin() as c:
        c.execute(text(f"UPDATE {table} SET owner_id=owner_id"))


def test_migration_one_revision_preserves_1b_data(db, service, store):
    owner, content = saved(service)
    original = store.original(owner, content)
    config = Config("alembic.ini")
    with db.begin() as c:
        config.attributes["connection"] = c
        command.downgrade(config, "0001")
        assert "content_analysis" not in inspect(c).get_table_names()
        assert c.scalar(text("SELECT count(*) FROM content_item")) == 1
        command.upgrade(config, "head")
    assert store.original(owner, content) == original
    assert (
        ProcessPendingContent(SQLAlchemyAnalysisStore(db), FakeProcessor(), AnalysisConfig())
        .process_one(owner)
        .status
        == "SUCCEEDED"
    )


def test_real_pdf_pages_and_separator_coverage(db, service):
    from tests.integration.test_pdf import pdf_bytes

    owner = OwnerId(uuid4())
    service.ingest(
        owner,
        "analysis-pdf",
        (IntakeInput(source_type=SourceType.PDF, payload=pdf_bytes(), filename="synthetic.pdf"),),
    )
    store = SQLAlchemyAnalysisStore(db)
    fake = FakeProcessor(action=False)
    outcome = ProcessPendingContent(store, fake, AnalysisConfig()).process_one(owner)
    analysis = store.get(owner, outcome.analysis_id)
    assert analysis.coverage == "COMPLETE"
    assert {c.evidence[0].page for c in analysis.claims} == {1, 2}
    assert len(fake.requests) == 2  # Whitespace separator is recorded without an AI call.


def test_database_rejects_invalid_quote_and_missing_action_evidence(db, service):
    owner, _ = saved(service)
    store = SQLAlchemyAnalysisStore(db)
    result = ProcessPendingContent(store, FakeProcessor(), AnalysisConfig()).process_one(owner)
    analysis = store.get(owner, result.analysis_id)
    with pytest.raises(DBAPIError), db.begin() as c:
        c.execute(
            AnalysisEvidenceRow.__table__.insert().values(
                id=uuid4(),
                owner_id=owner,
                analysis_id=analysis.id,
                content_id=analysis.content_id,
                extraction_id=analysis.extraction_id,
                role="CLAIM",
                ordinal=0,
                evidence_ordinal=3,
                start=0,
                end=4,
                page=None,
                quote="fake",
            )
        )
    with pytest.raises(DBAPIError), db.begin() as c:
        c.execute(
            ActionProposalRow.__table__.insert().values(
                id=uuid4(),
                owner_id=owner,
                analysis_id=analysis.id,
                candidate_ordinal=1,
                title="No evidence",
                description="Invalid",
                kind="task",
                uncertainty="high",
            )
        )
