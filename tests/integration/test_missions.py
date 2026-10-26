from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from lazyresearch.application.intake_models import IntakeInput
from lazyresearch.application.mission_models import MissionError, MissionScope
from lazyresearch.application.missions import ResearchOperations
from lazyresearch.bootstrap import build_retrieval
from lazyresearch.domain.content import SourceType
from lazyresearch.domain.identity import OwnerId
from lazyresearch.infrastructure.config import Settings
from lazyresearch.infrastructure.persistence.mission_models import ResearchProposalRow, ResultRow
from lazyresearch.infrastructure.persistence.missions import PostgreSQLMissionStore
from tests.mission_helpers import FakePages, FakeSearch, FakeSynthesis, prepare

pytestmark = pytest.mark.integration


@pytest.fixture
def mission_setup(db, service):
    store = PostgreSQLMissionStore(db)
    pages, search, synthesis = FakePages(), FakeSearch(), FakeSynthesis()
    service.fetcher = pages
    retrieval = build_retrieval(Settings("postgresql://unused"), engine=db)
    ops = ResearchOperations(store, retrieval, service, search, synthesis)
    owner = OwnerId(uuid4())
    for i, value in enumerate(
        (
            "Battery installer quote EUR 6000. Apply by 2026-12-01.",
            "Battery electricity rate 0.30 EUR per kWh.",
        )
    ):
        service.ingest(
            owner,
            f"personal-{i}",
            (IntakeInput(source_type=SourceType.TEXT, payload=value.encode()),),
        )
    topic = store.create_topic(owner, "Home Battery Systems")
    return ops, owner, topic, pages, search, synthesis


def test_two_runs_changed_sources_actions_and_idempotency(db, mission_setup):
    ops, owner, topic, pages, search, synthesis = mission_setup
    scope = MissionScope(public=True, require_current=True)
    first = ops.store.create_mission(owner, topic.id, "Battery", scope)
    prepare(ops, owner, first.id)
    r1 = ops.store.publish(owner, first.id)
    assert ops.store.publish(owner, first.id) == r1
    pages.price = "4500"
    search.urls.append("https://example.com/battery-new")
    synthesis.recommendation = "Compare the lower price before requesting assessment."
    second = ops.store.create_mission(owner, topic.id, "Battery", scope)
    assert second.baseline_result_id == r1
    prepare(ops, owner, second.id)
    r2 = ops.store.publish(owner, second.id)
    assert ops.store.get_topic(owner, topic.id).current_result_id == r2
    assert [r.version for r in ops.store.versions(owner, topic.id)] == [1, 2]
    with ops.store.transaction() as s:
        changes = s.get(ResultRow, r2).payload["changes"]
        assert changes["changed_snapshots"]
        assert changes["new_sources"]
        assert changes["recommendations_changed"] and changes["actions_changed"]
        assert s.scalar(select(func.count()).select_from(ResearchProposalRow)) == 2
        proposal = s.scalar(select(ResearchProposalRow).where(ResearchProposalRow.result_id == r2))
        assert proposal.payload["deadline"]["normalized"] is None
    assert all("UNVERIFIED_SNIPPET" not in e.quote for e in ops.store.evidence(owner, second.id))
    assert all(e.locator().quote == e.quote for e in ops.store.evidence(owner, second.id))


def test_concurrent_out_of_order_publication_and_duplicate_retry(mission_setup):
    ops, owner, topic, *_ = mission_setup
    missions = [
        ops.store.create_mission(owner, topic.id, "Battery", MissionScope()) for _ in range(2)
    ]
    for m in missions:
        prepare(ops, owner, m.id)
    newer_done = Event()

    def older():
        assert newer_done.wait(10)
        return ops.store.publish(owner, missions[0].id)

    def newer():
        result = ops.store.publish(owner, missions[1].id)
        newer_done.set()
        return result

    with ThreadPoolExecutor(3) as pool:
        a, b = pool.submit(older), pool.submit(newer)
        old, new = a.result(), b.result()
        repeats = list(pool.map(lambda _: ops.store.publish(owner, missions[1].id), range(5)))
    assert repeats == [new] * 5
    assert ops.store.get_topic(owner, topic.id).current_result_id == new
    versions = ops.store.versions(owner, topic.id)
    assert [(r.version, r.run_sequence) for r in versions] == [(1, 2), (2, 1)]
    assert old != new


def test_concurrent_run_allocation_and_owner_isolation(mission_setup):
    ops, owner, topic, *_ = mission_setup
    with ThreadPoolExecutor(4) as pool:
        missions = list(
            pool.map(
                lambda _: ops.store.create_mission(owner, topic.id, "Battery", MissionScope()),
                range(8),
            )
        )
    assert sorted(m.run_sequence for m in missions) == list(range(1, 9))
    assert ops.store.get_topic(OwnerId(uuid4()), topic.id) is None
    assert ops.store.get_mission(OwnerId(uuid4()), missions[0].id) is None
    assert ops.store.create_topic(owner, topic.title).id != topic.id


@pytest.mark.parametrize("terminal", ["CANCELLED", "FAILED"])
def test_terminal_fences_publication(mission_setup, terminal):
    ops, owner, topic, *_ = mission_setup
    m = ops.store.create_mission(owner, topic.id, "Battery", MissionScope())
    prepare(ops, owner, m.id)
    ops.store.terminal(owner, m.id, terminal, terminal)
    with pytest.raises(MissionError):
        ops.store.publish(owner, m.id)
    assert not ops.store.versions(owner, topic.id)
    with pytest.raises(MissionError):
        ops.store.save_stage(owner, m.id, "late", {})


def test_public_disabled_and_stage_retry_reuses_completed_sources(mission_setup):
    ops, owner, topic, pages, search, synthesis = mission_setup
    m = ops.store.create_mission(owner, topic.id, "Battery", MissionScope(require_current=True))
    prepare(ops, owner, m.id)
    assert not search.calls and not pages.calls
    assert ops.store.publish(owner, m.id)
    m2 = ops.store.create_mission(
        owner, topic.id, "Battery", MissionScope(public=True, require_current=True)
    )
    prepare(ops, owner, m2.id)
    counts = len(pages.calls), len(search.calls), len(synthesis.calls)
    prepare(ops, owner, m2.id)
    assert counts == (len(pages.calls), len(search.calls), len(synthesis.calls))


def test_frozen_inputs_evidence_results_database_guards(db, mission_setup):
    ops, owner, topic, *_ = mission_setup
    m = ops.store.create_mission(owner, topic.id, "Battery", MissionScope())
    prepare(ops, owner, m.id)
    r = ops.store.publish(owner, m.id)
    for statement in (
        "UPDATE research_mission SET question='tamper'",
        "UPDATE research_evidence SET payload='{}'",
        "UPDATE research_result SET payload='{}'",
        "DELETE FROM research_proposal",
    ):
        with pytest.raises(DBAPIError), db.begin() as conn:
            conn.execute(text(statement))
    assert ops.store.get_result(owner, r) is not None


def test_empty_mission_does_not_publish(mission_setup):
    ops, _, _, *_ = mission_setup
    owner = OwnerId(uuid4())
    topic = ops.store.create_topic(owner, "empty")
    m = ops.store.create_mission(owner, topic.id, "Nothing", MissionScope())
    with pytest.raises(MissionError, match="NO_EVIDENCE"):
        prepare(ops, owner, m.id)
    assert not ops.store.versions(owner, topic.id)


@pytest.mark.parametrize("failure", ["timeout", "missing_key", "fetch", "duplicate"])
def test_public_failures_and_duplicate_budget(mission_setup, failure):
    from lazyresearch.application.intake_models import ErrorCode, SourceError
    from lazyresearch.application.mission_models import TransientMissionError

    ops, owner, topic, pages, search, _ = mission_setup
    if failure in {"timeout", "missing_key"}:

        def unavailable(query, limit):
            raise (
                TransientMissionError("SEARCH_UNAVAILABLE")
                if failure == "timeout"
                else MissionError("SEARCH_NOT_CONFIGURED")
            )

        search.search = unavailable
    elif failure == "fetch":

        def inaccessible(url):
            raise SourceError(ErrorCode.PRIVATE_NETWORK_BLOCKED)

        pages.fetch = inaccessible
    else:
        search.urls *= 3
    m = ops.store.create_mission(
        owner, topic.id, "Battery", MissionScope(public=True, require_current=True, max_sources=2)
    )
    prepare(ops, owner, m.id)
    result = ops.store.get_result(owner, ops.store.publish(owner, m.id))
    if failure != "duplicate":
        assert result.coverage.value == "PARTIAL"
        assert result.limitations
    else:
        assert len(pages.calls) == 2


def test_collection_scope_and_invalid_frozen_locator(mission_setup):
    ops, owner, topic, *_ = mission_setup
    collection = ops.retrieval.store.create_collection(owner, "Chosen")
    m = ops.store.create_mission(
        owner, topic.id, "Battery", MissionScope(collection_ids=(collection,))
    )
    ops.store.start(owner, m.id)
    ops.personal_search(owner, m.id)
    assert ops.store.stage(owner, m.id, "personal_search")["evidence"] == []
    m2 = ops.store.create_mission(owner, topic.id, "Battery", MissionScope())
    ops.store.start(owner, m2.id)
    ops.personal_search(owner, m2.id)
    from lazyresearch.application.missions import evidence_values

    evidence = evidence_values(ops.store.stage(owner, m2.id, "personal_search"))
    with pytest.raises(MissionError):
        ops.store.freeze(owner, m2.id, (evidence[0].model_copy(update={"quote": "tampered"}),))
    with pytest.raises(MissionError):
        ops.store.freeze(owner, m2.id, (evidence[0].model_copy(update={"owner_id": uuid4()}),))


OFFICE_QUESTION = "What should we verify before choosing office software?"


@pytest.fixture
def office_mission_setup(mission_setup):
    ops, owner, _, pages, search, synthesis = mission_setup
    receipt = ops.intake.ingest(
        owner,
        "office-note",
        (
            IntakeInput(
                source_type=SourceType.TEXT,
                title="Meeting notes about new office software",
                payload=(
                    b"Compare Tool B SSO support and Tool C data export capability before deciding."
                ),
            ),
        ),
    )
    content = receipt.entries[0].content_id
    collection = ops.retrieval.store.create_collection(owner, "Office software")
    ops.retrieval.store.add_to_collection(owner, collection, content)
    ops.retrieval.store.index(owner, ops.retrieval.chunks)
    topic = ops.store.create_topic(owner, "Office software")
    return ops, owner, topic, collection, content


def test_office_question_empty_lexical_match_uses_scoped_evidence_without_relaxing_freeze(
    db, office_mission_setup
):
    from lazyresearch.application.retrieval_models import RetrievalRequest
    from lazyresearch.infrastructure.persistence.mission_models import MissionRow

    ops, owner, topic, collection, content = office_mission_setup
    scope = MissionScope(collection_ids=(collection,), public=False)
    request = RetrievalRequest(owner, OFFICE_QUESTION, collection_ids=(collection,))
    assert ops.retrieval.retrieve(request).candidates == ()
    # Persist the actual old search result and reproduce its rejected application operation.
    failed = ops.store.create_mission(owner, topic.id, OFFICE_QUESTION, scope)
    ops.store.start(owner, failed.id)
    ops.store.save_stage(owner, failed.id, "personal_search", {"evidence": [], "limitations": []})
    ops.gap_detection(owner, failed.id)
    ops.select_sources(owner, failed.id)
    with pytest.raises(MissionError, match="^NO_EVIDENCE$"):
        ops.freeze_evidence(owner, failed.id)
    ops.store.terminal(owner, failed.id, "FAILED", "WORKFLOW_FAILED")
    clean = ops.store.create_mission(owner, topic.id, OFFICE_QUESTION, scope)
    prepare(ops, owner, clean.id)
    evidence = ops.store.evidence(owner, clean.id)
    assert evidence and {e.content_id for e in evidence} == {content}
    assert {e.method for e in evidence} == {"collection_context"}
    ops.store.validate_evidence(owner, clean.id)
    ops.freeze_evidence(owner, clean.id)  # Already frozen retry remains idempotent.
    result = ops.store.publish(owner, clean.id)
    assert ops.store.publish(owner, clean.id) == result
    saved = ops.store.get_result(owner, result)
    assert saved.coverage.value == "PARTIAL"
    assert "selected_collection_context_used_without_question_match" in saved.limitations
    assert len(ops.store.versions(owner, topic.id)) == 1
    assert not ops.search.calls and not ops.intake.fetcher.calls
    with db.connect() as c:
        assert (
            c.execute(select(MissionRow.status).where(MissionRow.id == failed.id)).scalar_one()
            == "FAILED"
        )
        assert (
            c.execute(select(MissionRow.frozen).where(MissionRow.id == failed.id)).scalar_one()
            is False
        )
        assert (
            c.execute(
                select(func.count()).select_from(ResultRow).where(ResultRow.mission_id == clean.id)
            ).scalar_one()
            == 1
        )


def test_collection_context_is_explicit_bounded_owner_scoped_and_excludes_hidden(
    office_mission_setup,
):
    from lazyresearch.application.retrieval_models import RetrievalRequest

    ops, owner, topic, collection, content = office_mission_setup
    store = ops.retrieval.store
    request = RetrievalRequest(
        owner, OFFICE_QUESTION, collection_ids=(collection,), limit=2, per_source=1
    )
    another = (
        ops.intake.ingest(
            owner,
            "second-office",
            (
                IntakeInput(
                    source_type=SourceType.TEXT,
                    payload=b"Check licensing. " * 150,
                ),
            ),
        )
        .entries[0]
        .content_id
    )
    store.add_to_collection(owner, collection, another)
    store.index(owner, ops.retrieval.chunks)
    context = store.collection_context(request, ops.retrieval.chunks.identity)
    assert len(context) == 2 and {c.chunk.content_id for c in context} == {content, another}
    assert (
        store.collection_context(replace(request, collection_ids=()), ops.retrieval.chunks.identity)
        == ()
    )
    assert (
        store.collection_context(
            replace(request, owner_id=OwnerId(uuid4())), ops.retrieval.chunks.identity
        )
        == ()
    )
    store.set_visibility(owner, another, "DELETED")
    assert {
        c.chunk.content_id for c in store.collection_context(request, ops.retrieval.chunks.identity)
    } == {content}
    empty = store.create_collection(owner, "Empty collection")
    mission = ops.store.create_mission(
        owner, topic.id, OFFICE_QUESTION, MissionScope(collection_ids=(empty,))
    )
    with pytest.raises(MissionError, match="NO_EVIDENCE"):
        prepare(ops, owner, mission.id)
    assert not ops.store.versions(owner, topic.id)
