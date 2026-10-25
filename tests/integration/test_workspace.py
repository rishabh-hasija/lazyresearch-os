from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import event, update
from sqlalchemy.exc import DBAPIError
from streamlit.testing.v1 import AppTest

from lazyresearch.application.analysis import ProcessPendingContent
from lazyresearch.application.analysis_models import AnalysisConfig
from lazyresearch.application.mission_models import MissionError
from lazyresearch.application.missions import ResearchOperations
from lazyresearch.application.relevance_models import Relevance
from lazyresearch.bootstrap import build_retrieval, build_workspace
from lazyresearch.domain.actions import ActionStatus, Deadline
from lazyresearch.domain.identity import OwnerId
from lazyresearch.infrastructure.config import Settings
from lazyresearch.infrastructure.persistence.analysis import SQLAlchemyAnalysisStore
from lazyresearch.infrastructure.persistence.workspace_models import ActionItemRow
from lazyresearch.ports.errors import RepositoryConflict
from lazyresearch.ui.presenters import inputs
from tests.analysis_helpers import FakeProcessor
from tests.mission_helpers import FakeSearch, FakeSynthesis, prepare

pytestmark = pytest.mark.integration
APP = Path(__file__).resolve().parents[2] / "src/lazyresearch/ui/app.py"


@pytest.fixture
def work(db):
    settings = Settings("postgresql://unused")
    instance = build_workspace(settings, engine=db, env={"UI_OWNER_ID": str(uuid4())})
    instance.processing = lambda: ProcessPendingContent(
        SQLAlchemyAnalysisStore(db), FakeProcessor(deadline=None), AnalysisConfig()
    )
    instance.research_health = lambda: (_ for _ in ()).throw(
        AssertionError("automatic health probe")
    )
    return instance


def app(work, section="Add Sources"):
    at = AppTest.from_file(str(APP), default_timeout=15)
    at.session_state["workspace"] = work
    at.run()
    next(b for b in at.sidebar.button if b.label == section).click().run()
    assert not at.exception and not at.error
    return at


def test_demo_idempotent_action_lifecycle_edits_and_originals(db, work):
    receipt = work.load_demo()
    assert work.load_demo() == receipt
    assert work.process() == "SUCCEEDED"
    item = work.actions()[0]
    original = item.proposal
    work.change_action(item, ActionStatus.ACCEPTED)
    accepted = next(a for a in work.actions() if a.id == item.id)
    assert accepted.status == ActionStatus.ACCEPTED and accepted.revision == 1
    with pytest.raises(RepositoryConflict):
        work.change_action(item, ActionStatus.DISMISSED)
    work.change_action(
        accepted, title="My reviewed task", description="My own notes", deadline=Deadline()
    )
    edited = next(a for a in work.actions() if a.id == item.id)
    assert edited.proposal == original and edited.deadline == Deadline()
    work.change_action(edited, ActionStatus.COMPLETED)
    completed = next(a for a in work.actions() if a.id == item.id)
    work.change_action(completed, ActionStatus.ACCEPTED)
    assert next(a for a in work.actions() if a.id == item.id).revision == 4
    assert work.tasks.get(OwnerId(uuid4()), item.id) is None
    assert work.reads.source(OwnerId(uuid4()), receipt.entries[0].content_id) is None
    with pytest.raises(RepositoryConflict):
        work.tasks.save(OwnerId(uuid4()), item, expected_revision=None)


def test_two_concurrent_user_edits_only_one_wins(work):
    work.load_demo()
    work.process()
    item = work.actions()[0]
    work.tasks.save(work.owner, item, expected_revision=None)

    def save(title):
        try:
            work.change_action(item, title=title)
            return True
        except RepositoryConflict:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(save, ("Edit one", "Edit two"))) == [False, True]


def test_task_sql_identity_provenance_revision_and_migration_drift(db, work):
    work.load_demo()
    work.process()
    item = work.actions()[0]
    work.tasks.save(work.owner, item, expected_revision=None)
    work.tasks.save(work.owner, item, expected_revision=None)
    for values in (
        {"proposal_id": uuid4(), "revision": 1},
        {"revision": 0},
        {"status": "COMPLETED", "revision": 1},
    ):
        with pytest.raises(DBAPIError), db.begin() as c:
            c.execute(update(ActionItemRow).where(ActionItemRow.id == item.id).values(**values))
    config = Config("alembic.ini")
    with db.begin() as c:
        config.attributes["connection"] = c
        command.downgrade(config, "0005")
        command.upgrade(config, "head")
        command.check(config)


def test_feedback_stale_correction_and_collection_scope(db, work):
    work.load_demo()
    decision = work.catch_up()[0]
    event = work.feedback(decision, Relevance.READ)
    with pytest.raises(RepositoryConflict):
        work.feedback(decision, Relevance.IGNORE)
    work.feedback(decision, Relevance.KEEP, expected_event=event)
    assert work.ranking.store.history(work.owner, datetime.now(UTC))[0].label == Relevance.KEEP
    retrieval = build_retrieval(Settings("postgresql://unused"), engine=db)
    collection = retrieval.store.create_collection(work.owner, "Home Energy")
    receipt = work.add("collection", inputs("", (), "Battery note", "Note"), collection=collection)
    assert receipt.saved == 1
    with pytest.raises(RepositoryConflict):
        work.add("invalid-collection", inputs("", (), "Private", ""), collection=uuid4())


def test_research_projection_history_citations_and_research_action(db, work):
    work.load_demo()
    topic = work.mission_commands.create_topic(work.owner, "Battery")
    synthesis = FakeSynthesis()
    ops = ResearchOperations(
        work.mission_commands,
        build_retrieval(Settings("postgresql://unused"), engine=db),
        work.intake,
        FakeSearch(),
        synthesis,
    )
    first = work.research(topic.id, "Battery", public=False)
    prepare(ops, work.owner, first)
    r1 = ops.store.publish(work.owner, first)
    at = app(work, "Research")
    assert at.selectbox[-1].value == r1
    synthesis.recommendation = "Compare warranty before deciding."
    second = work.research(topic.id, "Battery", public=False)
    prepare(ops, work.owner, second)
    r2 = ops.store.publish(work.owner, second)
    versions = work.reads.results(work.owner, topic.id)
    assert [r.id for r in versions] == [r2, r1]
    assert versions[0].baseline_version == 1
    assert versions[0].payload["changes"]["recommendations_changed"]
    assert work.reads.result(OwnerId(uuid4()), r2) is None
    assert work.reads.missions(OwnerId(uuid4()), topic.id) == ()
    items = work.actions()
    assert len(items) == 2 and all(a.proposal.origin.result_id for a in items)
    work.change_action(items[0], ActionStatus.ACCEPTED)
    assert work.tasks.get(work.owner, items[0].id).status == ActionStatus.ACCEPTED
    at.run()
    assert at.selectbox[-1].value == r2
    assert any("Current Brief" in option for option in at.selectbox[-1].options)
    assert any("Previous version" in option for option in at.selectbox[-1].options)
    assert any("Evidence links validated" in caption.value for caption in at.caption)
    assert not at.json
    at.selectbox[-1].set_value(r1).run()
    assert at.selectbox[-1].value == r1
    assert any("Published version 1" in c.value for c in at.caption)


def test_streamlit_empty_pages_and_bad_source_sibling(work):
    at = app(work)
    assert any("No saved sources" in info.value for info in at.info)
    at.text_area[0].set_value("file:///not-allowed")
    at.text_area[1].set_value("Battery apply by 2026-11-07.")
    at.text_input[0].set_value("A saved note")
    next(b for b in at.button if b.label == "Save sources").click().run()
    assert not at.exception and not at.error
    assert len(work.reads.sources(work.owner)) == 1
    assert work.intake.store.batch(work.owner, at.session_state["receipt"].batch_id).failed == 1
    next(b for b in at.sidebar.button if b.label == "What Matters").click().run()
    assert any("baseline" in info.value for info in at.info)
    assert not at.exception and not at.error
    at.selectbox[0].set_value("ACT")
    next(button for button in at.button if button.label == "Save feedback").click().run()
    assert len(work.ranking.store.history(work.owner, datetime.now(UTC))) == 1
    next(b for b in at.sidebar.button if b.label == "Research").click().run()
    assert any("Create a topic" in info.value for info in at.info)
    next(b for b in at.sidebar.button if b.label == "Actions").click().run()
    assert any("No proposed actions" in info.value for info in at.info)


def test_streamlit_upload_processing_and_action_buttons(work):
    at = app(work)
    at.file_uploader[0].set_value(
        [
            ("notice.txt", b"Submit by 2026-11-07.", "text/plain"),
            ("invalid.pdf", b"%PDF-invalid", "application/pdf"),
        ]
    )
    next(button for button in at.button if button.label == "Save sources").click().run()
    assert not at.exception and not at.error and len(work.reads.sources(work.owner)) == 2
    next(button for button in at.button if button.label == "Analyze next source").click().run()
    assert not at.exception and not at.error
    next(b for b in at.sidebar.button if b.label == "Actions").click().run()
    next(button for button in at.button if button.label == "Accept").click().run()
    next(button for button in at.button if button.label == "Complete").click().run()
    next(button for button in at.button if button.label == "Reopen").click().run()
    assert work.actions()[0].status == ActionStatus.ACCEPTED


def test_streamlit_sanitizes_service_failure(work):
    work.processing = lambda: (_ for _ in ()).throw(RuntimeError("SECRET: no Ollama"))
    at = app(work)
    next(button for button in at.button if button.label == "Analyze next source").click().run()
    assert at.error and "SECRET" not in at.error[0].value and not at.exception


def test_partial_brief_warns_and_retains_exact_source_evidence(db, work):
    class UnavailableSearch:
        def search(self, query, limit):
            raise MissionError("SEARCH_UNAVAILABLE")

    work.load_demo()
    topic = work.mission_commands.create_topic(work.owner, "Partial battery research")
    work.scope = work.scope.model_copy(update={"require_current": True})
    ops = ResearchOperations(
        work.mission_commands,
        build_retrieval(Settings("postgresql://unused"), engine=db),
        work.intake,
        UnavailableSearch(),
        FakeSynthesis(),
    )
    mission = work.research(topic.id, "Battery", public=True)
    prepare(ops, work.owner, mission)
    identity = ops.store.publish(work.owner, mission)
    result = work.reads.result(work.owner, identity)
    assert result.coverage == "PARTIAL" and result.payload["limitations"]
    at = app(work, "Research")
    assert any("Partial coverage" in w.value for w in at.warning)
    assert any("Synthetic battery" in m.value for m in at.markdown)
    assert not at.error and not at.exception


def test_navigation_selected_state_persistent_header_and_public_warning(work, monkeypatch):
    monkeypatch.setenv("APP_ENV", "demo")
    at = app(work)
    for section in ("What Matters", "Research", "Actions", "Add Sources"):
        next(b for b in at.sidebar.button if b.label == section).click().run()
        assert not at.exception and not at.error
        assert at.session_state["workspace"] is work
        assert at.session_state["workspace-section"] == section
        assert len([t for t in at.title if t.value == "LazyResearch OS"]) == 1
        buttons = [
            b
            for b in at.sidebar.button
            if b.label in {"Add Sources", "What Matters", "Research", "Actions"}
        ]
        assert len(buttons) == 4
        assert [b.label for b in buttons if b.proto.type == "primary"] == [section]
        assert not at.sidebar.radio
        assert at.header[0].value == section
        assert all("Catch Up" not in node.value for node in at.header)
        warning = " ".join(node.value for node in at.warning)
        assert "shared synthetic workspace" in warning and "no authentication" in warning
        assert "persists in Neon (PostgreSQL), not temporary browser storage" in warning
        assert "Do NOT upload personal or private information" in warning


def test_closed_details_are_lazy_and_open_source_reads_fresh(work, monkeypatch):
    receipt = work.load_demo()
    at = app(work)
    details = [panel for panel in at.expander if panel.label.startswith("Synthetic battery")]
    assert len(details) == 2
    assert not any("Extraction:" in node.value for node in at.markdown)
    identity = receipt.entries[0].content_id
    at.session_state[f"saved-source-{identity}"] = True
    at.run()
    assert not at.exception and not at.error
    assert any("Extraction:" in node.value for node in at.markdown)


def test_evidence_read_is_one_query_with_scope_quote_and_deletion_checks(db, work):
    work.load_demo()
    work.process()
    locator = work.actions()[0].proposal.evidence[0]
    source = work.reads.source(work.owner, locator.content_id)
    statements = []

    def count(*args):
        statements.append(args[2])

    event.listen(db, "before_cursor_execute", count)
    try:
        assert work.reads.evidence(work.owner, locator) == (source.title, source.url)
        assert len(statements) == 1
    finally:
        event.remove(db, "before_cursor_execute", count)
    assert work.reads.evidence(OwnerId(uuid4()), locator) is None
    assert work.reads.evidence(work.owner, replace(locator, quote="X" * len(locator.quote))) is None
    assert work.reads.evidence(work.owner, replace(locator, extraction_id=uuid4())) is None
    retrieval = build_retrieval(Settings("postgresql://unused"), engine=db)
    work.index(work.owner)
    for visibility in ("DELETION_PENDING", "DELETED"):
        retrieval.store.set_visibility(work.owner, locator.content_id, visibility)
        assert work.reads.evidence(work.owner, locator) is None
