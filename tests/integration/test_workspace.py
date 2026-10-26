import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import event, select, text, update
from sqlalchemy.exc import DBAPIError
from streamlit.testing.v1 import AppTest

from lazyresearch.application.analysis import ProcessPendingContent
from lazyresearch.application.analysis_models import AnalysisConfig
from lazyresearch.application.mission_models import MissionError, MissionEvidence
from lazyresearch.application.missions import ResearchOperations
from lazyresearch.application.relevance_models import Relevance
from lazyresearch.application.workspace import Workspace
from lazyresearch.bootstrap import build_retrieval, build_workspace
from lazyresearch.domain.actions import ActionStatus, Deadline
from lazyresearch.domain.identity import OwnerId
from lazyresearch.infrastructure.config import Settings
from lazyresearch.infrastructure.persistence.analysis import SQLAlchemyAnalysisStore
from lazyresearch.infrastructure.persistence.mission_models import MissionRow, ResultRow
from lazyresearch.infrastructure.persistence.models import ContentAnalysisRow, JobRow
from lazyresearch.infrastructure.persistence.ranking_models import InteractionRow
from lazyresearch.infrastructure.persistence.retrieval_models import MembershipRow
from lazyresearch.infrastructure.persistence.workspace_models import ActionItemRow
from lazyresearch.ports.errors import RepositoryConflict, RepositoryError
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
    assert work.process().status == "SUCCEEDED"
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
    assert at.selectbox[0].value is None
    at.selectbox[0].set_value(topic.id).run()
    assert any("Published version" in c.value for c in at.caption)
    at.session_state[f"research-history-{topic.id}"] = True
    at.run()
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
    next(box for box in at.selectbox if box.label == "Your choice").set_value("ACT")
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
    at.selectbox[0].set_value(topic.id).run()
    at.session_state[f"research-history-{topic.id}"] = True
    at.run()
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


def test_collection_creation_normalizes_reuses_and_scopes_names(db, work):
    for name in ("", "   ", "x" * 121):
        with pytest.raises(ValueError):
            work.create_collection(name)
    assert work.reads.collections(work.owner) == ()
    with ThreadPoolExecutor(max_workers=2) as pool:
        created = tuple(pool.map(work.create_collection, (" Office software ", "office SOFTWARE")))
    assert created[0] == created[1]
    collections = dict(work.reads.collections(work.owner))
    assert len(collections) == 1
    assert next(iter(collections.values())).strip() in ("Office software", "office SOFTWARE")
    other_owner = OwnerId(uuid4())
    other = work.reads.create_collection(other_owner, "Office software")
    assert other != created[0]
    assert work.reads.collections(other_owner) == ((other, "Office software"),)
    receipt = work.add(
        "created-collection",
        inputs("", (), "Synthetic office planning note", "Note"),
        collection=created[0],
    )
    with db.connect() as connection:
        assert connection.execute(
            select(MembershipRow.content_id).where(
                MembershipRow.owner_id == work.owner,
                MembershipRow.collection_id == created[0],
            )
        ).scalars().all() == [receipt.entries[0].content_id]


def test_inline_collection_creation_selects_and_assigns_saved_source(db, work):
    existing = work.create_collection("Existing")
    at = app(work)
    selector = next(box for box in at.selectbox if box.label == "Collection (optional)")
    assert selector.value is None and selector.options == ["No collection", "Existing"]
    at.text_area[1].set_value("Synthetic meeting note for the collection.")
    at.text_input[0].set_value("Meeting note")
    next(b for b in at.button if b.label == "+ Create collection").click().run()
    name_input = next(field for field in at.text_input if field.label == "Collection name")
    assert name_input.proto.placeholder == "e.g. Office software"
    name_input.set_value("   ")
    next(b for b in at.button if b.label == "Create collection").click().run()
    assert any("Enter a collection name" in warning.value for warning in at.warning)
    assert work.reads.collections(work.owner) == ((existing, "Existing"),)
    next(field for field in at.text_input if field.label == "Collection name").set_value(
        " Office software "
    )
    next(b for b in at.button if b.label == "Create collection").click().run()
    created = next(
        identity
        for identity, name in work.reads.collections(work.owner)
        if name == "Office software"
    )
    selector = next(box for box in at.selectbox if box.label == "Collection (optional)")
    assert selector.value == created
    assert selector.options == ["No collection", "Existing", "Office software"]
    assert at.text_area[1].value == "Synthetic meeting note for the collection."
    next(b for b in at.button if b.label == "+ Create collection").click().run()
    next(field for field in at.text_input if field.label == "Collection name").set_value(
        "office SOFTWARE"
    )
    next(b for b in at.button if b.label == "Create collection").click().run()
    assert len(work.reads.collections(work.owner)) == 2
    assert (
        next(box for box in at.selectbox if box.label == "Collection (optional)").value == created
    )
    assert not at.exception and not at.error
    next(b for b in at.button if b.label == "Save sources").click().run()
    assert not at.exception and not at.error
    source = work.reads.sources(work.owner)[0]
    assert source.title == "Meeting note"
    with db.connect() as connection:
        assert connection.execute(
            select(MembershipRow.content_id).where(
                MembershipRow.owner_id == work.owner,
                MembershipRow.collection_id == created,
            )
        ).scalars().all() == [source.id]


def test_live_legacy_workspace_is_recomposed_and_collection_persists(db, work, monkeypatch):
    # Keep real application methods/ports from a pre-collection Workspace class. This
    # models the instance surviving Streamlit's module reload, not a mocked repository.
    legacy_class = type(
        "Workspace",
        (),
        {
            name: value
            for name, value in Workspace.__dict__.items()
            if name not in {"create_collection", "__dict__", "__weakref__"}
        },
    )
    legacy = legacy_class.__new__(legacy_class)
    legacy.__dict__.update(work.__dict__)
    assert not hasattr(legacy, "create_collection")
    monkeypatch.setenv("DATABASE_URL", db.url.render_as_string(hide_password=False))
    monkeypatch.setenv("UI_OWNER_ID", str(work.owner))
    at = AppTest.from_file(str(APP), default_timeout=15)
    at.session_state["workspace"] = legacy
    at.run()
    rebuilt = at.session_state["workspace"]
    try:
        assert isinstance(rebuilt, Workspace) and rebuilt is not legacy
        at.text_input[0].set_value("Preserved meeting draft")
        at.text_area[1].set_value("Synthetic office software comparison notes.")
        next(b for b in at.button if b.label == "+ Create collection").click().run()
        next(field for field in at.text_input if field.label == "Collection name").set_value(
            "Office software"
        )
        next(b for b in at.button if b.label == "Create collection").click().run()
        assert not at.exception and not at.error and not at.warning
        identity = next(
            i for i, name in work.reads.collections(work.owner) if name == "Office software"
        )
        assert (
            next(box for box in at.selectbox if box.label == "Collection (optional)").value
            == identity
        )
        assert at.text_input[0].value == "Preserved meeting draft"
        assert at.text_area[1].value == "Synthetic office software comparison notes."
        next(b for b in at.button if b.label == "Save sources").click().run()
        assert not at.exception and not at.error
        source = work.reads.sources(work.owner)[0]
        with db.connect() as connection:
            assert connection.execute(
                select(MembershipRow.content_id).where(
                    MembershipRow.owner_id == work.owner,
                    MembershipRow.collection_id == identity,
                )
            ).scalars().all() == [source.id]
    finally:
        if rebuilt is not legacy:
            rebuilt.reads.engine.dispose()


def test_collection_database_failure_logs_diagnostics_without_payloads(db, work, caplog):
    # An actual PostgreSQL insert rejection exercises the repository's exception chain.
    with db.begin() as connection:
        connection.execute(
            text("ALTER TABLE collection ADD CONSTRAINT test_collection_rejection CHECK (false)")
        )
    at = app(work)
    at.text_input[0].set_value("PRIVATE draft title")
    at.text_area[1].set_value("PRIVATE draft text")
    next(b for b in at.button if b.label == "+ Create collection").click().run()
    next(field for field in at.text_input if field.label == "Collection name").set_value(
        "PRIVATE collection name"
    )
    next(b for b in at.button if b.label == "Create collection").click().run()
    assert not at.exception and not at.error and at.warning
    assert "RepositoryConflict" in caplog.text and "IntegrityError" in caplog.text
    assert "sqlstate=23514" in caplog.text and "create_collection" in caplog.text
    assert "PRIVATE" not in caplog.text
    assert all("PRIVATE" not in warning.value for warning in at.warning)
    assert at.text_input[0].value == "PRIVATE draft title"
    assert at.text_area[1].value == "PRIVATE draft text"
    assert work.reads.collections(work.owner) == ()


def test_analysis_reports_exact_new_source_before_older_config_refresh(db, work):
    # Match the owner failure: a saved source has analysis at timeout=240, then the
    # web's timeout=120 creates a refresh job ahead of a never-analyzed meeting note.
    store = SQLAlchemyAnalysisStore(db)
    old_config = AnalysisConfig(timeout_seconds=240)
    work.processing = lambda: ProcessPendingContent(store, FakeProcessor(deadline=None), old_config)
    old_receipt = work.add(
        "old-analyzed", inputs("", (), "Existing saved document", "Earlier source")
    )
    original_analysis = work.process().analysis_id
    current_config = replace(old_config, timeout_seconds=120)
    current_processor = FakeProcessor(deadline=None)
    current = ProcessPendingContent(store, current_processor, current_config)
    refresh = store.claim(work.owner, current_config)
    store.fail(refresh, "UNAVAILABLE", ())
    store.retry_failed(work.owner, refresh.lease.id)
    receipt = work.add(
        "new-meeting",
        inputs(
            "",
            (),
            "Compare office software and confirm SSO support.",
            "Meeting notes about new office software",
        ),
    )
    target = receipt.entries[0].content_id
    work.processing = lambda: current
    assert work.reads.source(work.owner, target).processing_status == "PENDING"
    at = app(work)
    next(b for b in at.button if b.label == "Analyze next source").click().run()
    assert not at.error and not at.exception
    assert any(
        s.value == "Analysis complete: Meeting notes about new office software" for s in at.success
    )
    assert not any(s.value == "Analysis ready." for s in at.success)
    assert any("1 source remains" in c.value for c in at.caption)
    assert current_processor.requests[0].content_id == target
    source = work.reads.source(work.owner, target)
    assert source.processing_status == "READY" and source.analysis is not None
    assert store.get(work.owner, original_analysis).content_id == old_receipt.entries[0].content_id
    with db.connect() as connection:
        assert (
            connection.execute(
                select(JobRow.status).where(JobRow.id == refresh.lease.id)
            ).scalar_one()
            == "PENDING"
        )
        assert (
            connection.execute(
                select(ContentAnalysisRow.job_id).where(ContentAnalysisRow.id == source.analysis.id)
            ).scalar_one()
            != refresh.lease.id
        )
    next(b for b in at.button if b.label == "Analyze next source").click().run()
    assert any(s.value == "Analysis complete: Earlier source" for s in at.success)
    assert not any("sources remain" in c.value for c in at.caption)
    assert store.get(work.owner, original_analysis) is not None


def test_analysis_failure_never_reports_success_and_retains_exact_source(db, work):
    receipt = work.add(
        "failed-meeting",
        inputs("", (), "Verify office software.", "Meeting notes about new office software"),
    )
    work.processing = lambda: ProcessPendingContent(
        SQLAlchemyAnalysisStore(db), FakeProcessor(error="UNAVAILABLE"), AnalysisConfig()
    )
    at = app(work)
    next(b for b in at.button if b.label == "Analyze next source").click().run()
    assert not at.exception and not at.success
    assert any(
        "Analysis failed: Meeting notes about new office software" in w.value for w in at.warning
    )
    source = work.reads.source(work.owner, receipt.entries[0].content_id)
    assert source.processing_status == "FAILED" and source.analysis is None
    assert source.text == "Verify office software."


@pytest.fixture
def collection_ranking_sources(work):
    office = work.create_collection("Office software")
    battery = work.create_collection("Home Battery")
    note = work.add(
        "office-task",
        inputs("", (), "Confirm SSO support.", "Meeting notes about new office software"),
        collection=office,
    )
    assert work.process().status == "SUCCEEDED"
    other = work.add(
        "office-reference",
        inputs("", (), "Software reference.", "Office reference"),
        collection=office,
    )
    demo = work.add(
        "battery-note", inputs("", (), "Battery comparison.", "Battery demo"), collection=battery
    )
    unfiled = work.add("unfiled-note", inputs("", (), "Unfiled note.", "Unfiled source"))
    return office, battery, tuple(r.entries[0].content_id for r in (note, other, demo, unfiled))


def test_collection_ranking_query_scopes_before_limit_and_preserves_owner(
    work, collection_ranking_sources
):
    office, battery, (note, other, demo, unfiled) = collection_ranking_sources
    all_sources = work.catch_up()
    assert {d.item.content_id for d in all_sources} == {note, other, demo, unfiled}
    assert {d.item.content_id for d in work.catch_up(collection_id=office)} == {note, other}
    assert {d.item.content_id for d in work.catch_up(collection_id=battery)} == {demo}
    # The latest workspace source is unfiled; filter must run before limit=1.
    ranked = work.ranking.rank(work.owner, datetime.now(UTC), limit=1, collection_id=office)
    assert len(ranked) == 1 and ranked[0].item.content_id in {note, other}
    foreign = work.reads.create_collection(OwnerId(uuid4()), "Foreign office")
    assert work.catch_up(collection_id=foreign) == ()
    assert work.catch_up(collection_id=uuid4()) == ()
    assert work.reviewed(demo, collection_id=office) is None
    assert work.reviewed(note, collection_id=office).item.content_id == note
    exact = work.reviewed(note, ("Applications",), collection_id=office)
    partial = work.reviewed(note, ("application",), collection_id=office)
    assert exact.item.features.interest_overlap == 1
    assert partial.item.features.interest_overlap == 0


def test_what_matters_collection_counts_feedback_and_session_retention(
    work, collection_ranking_sources
):
    office, battery, (note, other, demo, unfiled) = collection_ranking_sources
    at = app(work, "What Matters")
    selector = next(box for box in at.selectbox if box.label == "Collection")
    assert selector.value is None
    assert selector.options == ["All sources", "Home Battery", "Office software"]
    assert {metric.label: metric.value for metric in at.metric} == {
        "Read now": "3",
        "Useful later": "0",
        "Action required": "1",
        "Low priority": "0",
    }
    interests = at.text_input[0]
    assert interests.label == "What are you interested in right now? (optional)"
    assert interests.proto.placeholder == "e.g. work software, travel plans, home renovation"
    assert "Leave it blank" in interests.proto.help
    selector.set_value(office).run()
    assert {d.item.content_id for d in at.session_state["ranking"]} == {note, other}
    assert not any("Battery demo" in m.value or "Unfiled source" in m.value for m in at.markdown)
    assert {metric.label: metric.value for metric in at.metric} == {
        "Read now": "1",
        "Useful later": "0",
        "Action required": "1",
        "Low priority": "0",
    }
    next(box for box in at.selectbox if box.label == "Your choice").set_value("KEEP")
    next(b for b in at.button if b.label == "Save feedback").click().run()
    history = work.ranking.store.history(work.owner, datetime.now(UTC))
    assert len(history) == 1 and history[0].item.content_id == other
    assert history[0].label == Relevance.KEEP
    assert {metric.label: metric.value for metric in at.metric} == {
        "Read now": "0",
        "Useful later": "1",
        "Action required": "1",
        "Low priority": "0",
    }
    next(b for b in at.sidebar.button if b.label == "Actions").click().run()
    next(b for b in at.sidebar.button if b.label == "What Matters").click().run()
    assert next(box for box in at.selectbox if box.label == "Collection").value == office
    next(box for box in at.selectbox if box.label == "Collection").set_value(battery).run()
    assert {d.item.content_id for d in at.session_state["ranking"]} == {demo}
    assert {metric.label: metric.value for metric in at.metric} == {
        "Read now": "1",
        "Useful later": "0",
        "Action required": "0",
        "Low priority": "0",
    }
    next(box for box in at.selectbox if box.label == "Collection").set_value(None).run()
    assert {d.item.content_id for d in at.session_state["ranking"]} == {note, demo, unfiled}
    assert not at.error and not at.exception


def test_add_sources_collection_selection_carries_into_what_matters(work):
    at = app(work)
    next(b for b in at.button if b.label == "+ Create collection").click().run()
    next(field for field in at.text_input if field.label == "Collection name").set_value(
        "Office software"
    )
    next(b for b in at.button if b.label == "Create collection").click().run()
    office = next(i for i, name in work.reads.collections(work.owner) if name == "Office software")
    next(b for b in at.sidebar.button if b.label == "What Matters").click().run()
    assert next(box for box in at.selectbox if box.label == "Collection").value == office
    assert all(metric.value == "0" for metric in at.metric)
    battery = work.create_collection("Home Battery")
    next(b for b in at.sidebar.button if b.label == "Add Sources").click().run()
    next(box for box in at.selectbox if box.label == "Collection (optional)").set_value(battery)
    at.text_area[1].set_value("Synthetic battery sample")
    next(b for b in at.button if b.label == "Save sources").click().run()
    next(b for b in at.sidebar.button if b.label == "What Matters").click().run()
    assert next(box for box in at.selectbox if box.label == "Collection").value == battery
    assert len(at.session_state["ranking"]) == 1
    # Other browser sessions still start with All sources; no global preference was saved.
    fresh = app(work, "What Matters")
    assert next(box for box in fresh.selectbox if box.label == "Collection").value is None
    assert not at.error and not at.exception


FEEDBACK_CONFIRMATION = "Saved. LazyResearch will use this choice to learn your preferences."


@pytest.fixture
def feedback_ui(work):
    office = work.create_collection("Office software")
    receipt = work.add(
        "feedback-meeting",
        inputs("", (), "Confirm software requirements.", "Meeting notes about new office software"),
        collection=office,
    )
    assert work.process().status == "SUCCEEDED"
    at = app(work, "What Matters")
    next(box for box in at.selectbox if box.label == "Collection").set_value(office).run()
    return at, receipt.entries[0].content_id


def feedback_rows(db, owner, content):
    with db.connect() as connection:
        return connection.execute(
            select(InteractionRow.id, InteractionRow.label, InteractionRow.supersedes)
            .where(
                InteractionRow.owner_id == owner,
                InteractionRow.content_id == content,
                InteractionRow.kind == "FEEDBACK_LABELED",
            )
            .order_by(InteractionRow.recorded_at)
        ).all()


def test_feedback_confirmation_is_inside_form_after_real_commit(db, work, feedback_ui):
    at, content = feedback_ui
    next(b for b in at.button if b.label == "Save feedback").click().run()
    persisted = feedback_rows(db, work.owner, content)
    assert len(persisted) == 1 and persisted[0].label == "ACT"
    assert not at.exception and not at.error
    assert any(
        any(b.label == "Save feedback" for b in form.button)
        and any(s.value == FEEDBACK_CONFIRMATION for s in form.success)
        for form in at.get("form")
    )
    at.run()
    assert any(s.value == FEEDBACK_CONFIRMATION for s in at.success)
    assert len(feedback_rows(db, work.owner, content)) == 1
    next(b for b in at.button if b.label == "Save feedback").click().run()
    revised = feedback_rows(db, work.owner, content)
    assert len(revised) == 2 and revised[1].supersedes == persisted[0].id
    assert any(s.value == FEEDBACK_CONFIRMATION for s in at.success)


def test_feedback_commit_failure_replaces_old_success_with_sanitized_error(db, work, feedback_ui):
    at, content = feedback_ui
    next(b for b in at.button if b.label == "Save feedback").click().run()
    committed = feedback_rows(db, work.owner, content)
    assert len(committed) == 1 and at.success
    # A real deferred PostgreSQL rejection proves that success waits for COMMIT,
    # not merely a successful INSERT/flush. This affects only the test's schema.
    with db.begin() as connection:
        connection.execute(
            text("""
            CREATE FUNCTION reject_feedback_commit() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF NEW.kind = 'FEEDBACK_LABELED' THEN
                    RAISE EXCEPTION 'PRIVATE database failure' USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END $$
        """)
        )
        connection.execute(
            text("""
            CREATE CONSTRAINT TRIGGER reject_feedback_at_commit
            AFTER INSERT ON user_interaction DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION reject_feedback_commit()
        """)
        )
    next(b for b in at.button if b.label == "Save feedback").click().run()
    assert not at.exception and not at.success
    assert any("Could not save this choice." in e.value for e in at.error)
    assert all("PRIVATE" not in e.value for e in at.error)
    assert feedback_rows(db, work.owner, content) == committed
    assert at.session_state[f"feedback-event-{content}"] == committed[0].id


def test_feedback_commit_is_acknowledged_even_if_view_refresh_fails(
    db, work, feedback_ui, monkeypatch
):
    at, content = feedback_ui

    def unavailable(*args, **kwargs):
        raise RepositoryError("PRIVATE read failure")

    monkeypatch.setattr(work, "reviewed", unavailable)
    next(b for b in at.button if b.label == "Save feedback").click().run()
    assert len(feedback_rows(db, work.owner, content)) == 1
    assert any(s.value == FEEDBACK_CONFIRMATION for s in at.success)
    assert any(
        "Your choice was saved, but this view could not refresh" in w.value for w in at.warning
    )
    assert all("PRIVATE" not in w.value for w in at.warning)
    assert not at.exception and not at.error


def test_research_collection_context_explicit_topics_editable_scope_and_frozen_mission(db, work):
    office = work.create_collection("Office software")
    battery = work.create_collection("Home Battery")
    old = work.mission_commands.create_topic(work.owner, "Unrelated old battery research")
    at = app(work, "What Matters")
    next(b for b in at.selectbox if b.label == "Collection").set_value(office).run()
    next(b for b in at.sidebar.button if b.label == "Research").click().run()
    assert at.multiselect[0].value == [office]
    assert at.selectbox[0].value is None
    assert at.text_input[0].value == "Office software"
    assert any(b.label == "+ New research topic" for b in at.button)
    assert not any("Published version" in c.value for c in at.caption)
    next(b for b in at.button if b.label == "Create topic").click().run()
    selected = at.selectbox[0].value
    assert selected != old.id
    assert (
        next(t for t in work.reads.topics(work.owner) if t.id == selected).title
        == "Office software"
    )
    at.text_area[0].set_value("What should I verify?")
    next(b for b in at.button if b.label == "Start research").click().run()
    with db.connect() as connection:
        frozen = connection.execute(
            select(MissionRow.inputs).where(MissionRow.topic_id == selected)
        ).scalar_one()
    assert frozen["collection_ids"] == [str(office)] and not frozen["public"]
    # Explicit topic choices and cleared scope survive navigation's widget cleanup.
    at.multiselect[0].set_value([]).run()
    assert at.selectbox[0].value is None
    at.selectbox[0].set_value(old.id).run()
    next(b for b in at.sidebar.button if b.label == "Actions").click().run()
    assert at.selectbox[0].value is None
    next(b for b in at.sidebar.button if b.label == "Research").click().run()
    assert at.multiselect[0].value == [] and at.selectbox[0].value == old.id
    # A new collection context never silently picks an unrelated row.
    next(b for b in at.sidebar.button if b.label == "What Matters").click().run()
    at.selectbox[0].set_value(battery).run()
    next(b for b in at.sidebar.button if b.label == "Research").click().run()
    assert at.multiselect[0].value == [battery] and at.selectbox[0].value is None
    at.multiselect[0].set_value([office]).run()
    assert at.selectbox[0].value == selected
    next(b for b in at.sidebar.button if b.label == "Add Sources").click().run()
    assert next(b for b in at.selectbox if b.label == "Collection (optional)").value == office
    assert not at.error and not at.exception


@pytest.fixture
def action_collections(work):
    office = work.create_collection("Office software")
    battery = work.create_collection("Home Battery")
    for collection, title in (
        (office, "Meeting notes about new office software"),
        (battery, "Battery"),
    ):
        work.add(
            str(collection),
            inputs("", (), f"Comparison notes {title}.", title),
            collection=collection,
        )
        assert work.process().status == "SUCCEEDED"
    return office, battery


def test_actions_real_membership_scope_lifecycle_and_navigation(work, action_collections):
    office, battery = action_collections
    office_item = work.actions(collection_id=office)[0]
    battery_item = work.actions(collection_id=battery)[0]
    # Names cannot confer membership: intentionally misleading editable title.
    work.change_action(battery_item, title="Office software unrelated task")
    work.change_action(office_item, title="Confirm Tool B SSO support")
    original = office_item.proposal
    at = app(work, "What Matters")
    next(b for b in at.selectbox if b.label == "Collection").set_value(office).run()
    next(b for b in at.sidebar.button if b.label == "Actions").click().run()
    assert at.selectbox[0].value == office
    assert any("Confirm Tool B SSO support" in m.value for m in at.markdown)
    assert not any("Office software unrelated task" in m.value for m in at.markdown)
    assert any(c.value == "1 actions" for c in at.caption)
    for label in ("Accept", "Complete", "Reopen", "Dismiss", "Reopen"):
        next(b for b in at.button if b.label == label).click().run()
        assert at.selectbox[0].value == office
    item = work.actions(collection_id=office)[0]
    assert item.status == ActionStatus.ACCEPTED and item.proposal == original
    assert item.revision == 6  # one edit plus five transitions
    next(field for field in at.text_input if field.label == "Task title").set_value(
        "My reviewed software checks"
    )
    next(b for b in at.button if b.label == "Save task edits").click().run()
    item = work.actions(collection_id=office)[0]
    assert item.title == "My reviewed software checks" and item.revision == 7
    assert item.proposal == original and at.selectbox[0].value == office
    at.session_state[f"provenance-{item.id}"] = True
    at.run()
    assert any("Meeting notes about new office software" in m.value for m in at.markdown)
    assert any("Comparison notes" in m.value for m in at.markdown)
    at.selectbox[0].set_value(battery).run()
    assert any("Office software unrelated task" in m.value for m in at.markdown)
    assert not any("Confirm Tool B SSO support" in m.value for m in at.markdown)
    at.selectbox[0].set_value(None).run()
    assert len(work.actions()) == 2
    assert any(c.value == "2 actions" for c in at.caption)
    next(b for b in at.sidebar.button if b.label == "Research").click().run()
    assert at.multiselect[0].value == []
    next(b for b in at.sidebar.button if b.label == "What Matters").click().run()
    assert at.selectbox[0].value is None
    assert work.actions(collection_id=uuid4()) == ()
    assert not at.exception and not at.error


def test_research_actions_use_all_cited_source_memberships(db, work, action_collections):
    office, battery = action_collections
    topic = work.mission_commands.create_topic(work.owner, "Name cannot determine action scope")
    ops = ResearchOperations(
        work.mission_commands,
        build_retrieval(Settings("postgresql://unused"), engine=db),
        work.intake,
        FakeSearch(),
        FakeSynthesis(),
    )
    mixed_mission = work.research(topic.id, "Comparison", public=False)
    prepare(ops, work.owner, mixed_mission)
    mixed_result = ops.store.publish(work.owner, mixed_mission)
    mixed = next(a for a in work.actions() if a.proposal.origin.result_id == mixed_result)
    assert len({e.content_id for e in mixed.proposal.evidence}) == 2
    assert mixed.id not in {a.id for a in work.actions(collection_id=office)}
    assert mixed.id not in {a.id for a in work.actions(collection_id=battery)}
    scoped_mission = work.research(topic.id, "Comparison", public=False, collections=(office,))
    prepare(ops, work.owner, scoped_mission)
    scoped_result = ops.store.publish(work.owner, scoped_mission)
    scoped = next(
        a
        for a in work.actions(collection_id=office)
        if a.proposal.origin.result_id == scoped_result
    )
    assert scoped.proposal.evidence
    assert scoped.id not in {a.id for a in work.actions(collection_id=battery)}
    assert {a.id for a in work.actions()} >= {mixed.id, scoped.id}
    # The originating research result/evidence remains immutable across review.
    work.change_action(scoped, ActionStatus.ACCEPTED)
    assert (
        next(a for a in work.actions(collection_id=office) if a.id == scoped.id).proposal
        == scoped.proposal
    )


def test_just_completed_research_opens_its_brief_without_opening_old_history(db, work):
    work.load_demo()
    topic = work.mission_commands.create_topic(work.owner, "Battery")
    at = app(work, "Research")
    at.selectbox[0].set_value(topic.id).run()
    at.text_area[0].set_value("Battery")
    next(b for b in at.button if b.label == "Start research").click().run()
    mission = work.reads.missions(work.owner, topic.id)[0].id
    assert not any("Published version" in c.value for c in at.caption)
    ops = ResearchOperations(
        work.mission_commands,
        build_retrieval(Settings("postgresql://unused"), engine=db),
        work.intake,
        FakeSearch(),
        FakeSynthesis(),
    )
    prepare(ops, work.owner, mission)
    result = ops.store.publish(work.owner, mission)
    next(b for b in at.button if b.label == "Refresh research").click().run()
    assert not any(b.label in {"View result", "Open brief"} for b in at.button)
    assert any("Published version 1" in c.value for c in at.caption)
    assert not next(e for e in at.expander if e.label == "Previous research").proto.expanded
    assert work.reads.result(work.owner, result) is not None
    assert not at.error and not at.exception


@pytest.mark.parametrize("partial", [False, True], ids=["completed", "partial"])
def test_current_brief_renders_automatically_and_collapses_failed_attempts(db, work, partial):
    # COMPLETE has two matching sources; PARTIAL reproduces the one-source,
    # long-question collection-context fallback from the Office software walkthrough.
    office = work.create_collection("Office software")
    title = "Meeting notes about new office software"
    work.add(
        "office-notes",
        inputs("", (), "Compare office software SSO and export support.", title),
        collection=office,
    )
    if not partial:
        work.add(
            "office-notes-2",
            inputs("", (), "Verify office software costs.", "Cost notes"),
            collection=office,
        )
    topic = work.mission_commands.create_topic(work.owner, "Office software")
    failed = []
    for question in ("Earlier attempt one", "Earlier attempt two"):
        identity = work.research(topic.id, question, public=False, collections=(office,))
        work.mission_commands.terminal(work.owner, identity, "FAILED", "WORKFLOW_FAILED")
        failed.append(identity)
    question = "What should we verify before choosing office software?" if partial else "office"
    mission = work.research(topic.id, question, public=False, collections=(office,))

    class OptionalRecommendations(FakeSynthesis):
        def synthesize(self, request):
            output = super().synthesize(request)
            if partial:
                # The live Office software brief has no stored recommendations.
                output = output.model_copy(
                    update={"brief": output.brief.model_copy(update={"recommendations": ()})}
                )
            return output

    ops = ResearchOperations(
        work.mission_commands,
        build_retrieval(Settings("postgresql://unused"), engine=db),
        work.intake,
        FakeSearch(),
        OptionalRecommendations(),
    )
    prepare(ops, work.owner, mission)
    identity = ops.store.publish(work.owner, mission)
    before = work.reads.result(work.owner, identity)
    missions = work.reads.missions(work.owner, topic.id)
    assert missions[0].status == ("PARTIAL" if partial else "COMPLETED")
    assert missions[0].result_id == identity
    assert all(m.result_id is None for m in missions if m.id in failed)
    assert work.reads.missions(OwnerId(uuid4()), topic.id) == ()

    # Fresh session: never submitted here, so no follow-mission state can help.
    at = app(work, "Research")
    at.selectbox[0].set_value(topic.id).run()
    assert any(h.value == "Current research" for h in at.subheader)
    assert any(question in m.value for m in at.markdown)
    assert not any("Earlier attempt" in m.value for m in at.markdown)
    assert not any("Research could not finish" in w.value for w in at.warning)
    assert not next(e for e in at.expander if e.label == "Previous research").proto.expanded
    assert not any(b.label in {"View result", "Open brief"} for b in at.button)
    assert {"Answer", "Summary", "Findings", "Recommendations", "What changed"} <= {
        h.value for h in at.subheader
    }
    assert any("Published version 1" in c.value for c in at.caption)
    if partial:
        assert any("Partial coverage" in w.value for w in at.warning)
        assert any(
            c.value
            == "This result is based on limited evidence. Review the coverage limitations below."
            for c in at.caption
        )
        assert not any("Open it to review" in c.value for c in at.caption)
        assert any("no published recommendations" in c.value for c in at.caption)
        assert any("too few saved sources" in c.value for c in at.caption)
        assert any("matched every word of the question" in c.value for c in at.caption)
        assert {
            "insufficient_personal_sources",
            "selected_collection_context_used_without_question_match",
        } <= set(before.payload["limitations"])
        for limitation in before.payload["limitations"]:
            assert any(limitation.replace("_", " ") in m.value for m in at.markdown)
        assert {e["title"] for e in before.payload["evidence"]} == {title}
    claim = next(e for e in at.expander if e.label == "Evidence for answer 1")
    at.session_state[claim.key] = True
    at.run()
    for raw in before.payload["evidence"]:
        evidence = MissionEvidence.model_validate_json(json.dumps(raw))
        assert work.reads.evidence(work.owner, evidence.locator()) is not None
        assert any(raw["title"] in m.value for m in at.markdown)
        assert any(raw["quote"] in m.value for m in at.markdown)
    at.session_state[f"research-history-{topic.id}"] = True
    at.run()
    history = next(e for e in at.expander if e.label == "Previous research")
    assert all(
        any(q in m.value for m in history.markdown)
        for q in ("Earlier attempt one", "Earlier attempt two")
    )
    assert not any(b.label in {"View result", "Open brief"} for b in at.button)
    assert len([w for w in history.warning if "Research could not finish" in w.value]) == 2
    assert work.reads.result(work.owner, identity) == before
    with db.connect() as connection:
        assert (
            len(
                connection.execute(
                    select(ResultRow.id).where(ResultRow.mission_id == mission)
                ).all()
            )
            == 1
        )
    assert not at.error and not at.exception


def test_failed_rerun_keeps_current_brief_and_has_no_result_button(db, work):
    work.load_demo()
    topic = work.mission_commands.create_topic(work.owner, "Battery")
    ops = ResearchOperations(
        work.mission_commands,
        build_retrieval(Settings("postgresql://unused"), engine=db),
        work.intake,
        FakeSearch(),
        FakeSynthesis(),
    )
    # Finish an older request later: publication version must not choose Current Brief.
    older = work.research(topic.id, "Battery installer", public=False)
    newer = work.research(topic.id, "Battery", public=False)
    prepare(ops, work.owner, older)
    prepare(ops, work.owner, newer)
    current_result = ops.store.publish(work.owner, newer)
    older_result = ops.store.publish(work.owner, older)
    assert work.reads.result(work.owner, older_result).version == 2
    failure = work.research(topic.id, "A failed rerun", public=False)
    work.mission_commands.terminal(work.owner, failure, "FAILED", "WORKFLOW_FAILED")
    at = app(work, "Research")
    at.selectbox[0].set_value(topic.id).run()
    assert any(m.value == "**Battery**" for m in at.markdown)
    assert not any("failed rerun" in m.value for m in at.markdown)
    assert any("Published version 1" in c.value for c in at.caption)
    assert not any(b.label in {"View result", "Open brief"} for b in at.button)
    assert work.reads.topics(work.owner)[0].current_result_id == current_result
    at.session_state[f"research-history-{topic.id}"] = True
    at.run()
    history = next(e for e in at.expander if e.label == "Previous research")
    assert any("A failed rerun" in m.value for m in history.markdown)
    assert not any(b.key == f"view-result-{failure}" for b in history.button)
    assert any(b.key == f"view-result-{older}" for b in history.button)
    assert len([b for b in at.button if b.label == "Open brief"]) == 1
    assert not any(b.label == "View result" for b in at.button)
    next(b for b in history.button if b.label == "Open brief").click().run()
    assert at.session_state[f"research-open-{older}"]
    assert len([c for c in at.caption if "Published version 2" in c.value]) == 1
    assert not at.error and not at.exception


def test_failed_only_topic_has_no_brief_or_open_control(work):
    topic = work.mission_commands.create_topic(work.owner, "Failed research")
    mission = work.research(topic.id, "An unsuccessful question", public=False)
    work.mission_commands.terminal(work.owner, mission, "FAILED", "WORKFLOW_FAILED")
    at = app(work, "Research")
    at.selectbox[0].set_value(topic.id).run()
    assert any("No published brief yet" in i.value for i in at.info)
    assert not any("Published version" in c.value for c in at.caption)
    assert not any(h.value == "Answer" for h in at.subheader)
    at.session_state[f"research-history-{topic.id}"] = True
    at.run()
    history = next(e for e in at.expander if e.label == "Previous research")
    assert any("Research could not finish" in w.value for w in history.warning)
    assert not any(b.label in {"View result", "Open brief"} for b in at.button)
    assert not any("Published version" in c.value for c in at.caption)
    assert not any(h.value == "Answer" for h in at.subheader)
    assert not at.error and not at.exception
