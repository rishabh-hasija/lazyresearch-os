from dataclasses import FrozenInstanceError, replace
from datetime import datetime
from uuid import UUID

import pytest

from lazyresearch.domain.errors import (
    DomainError,
    InvalidResearchPublication,
    InvalidStateTransition,
    MissingProvenance,
)
from lazyresearch.domain.identity import MissionId, OwnerId, ResultId, TopicId
from lazyresearch.domain.research import (
    MissionStatus,
    ResearchMission,
    ResearchResult,
    ResearchTopic,
    ResultCoverage,
    plan_publication,
)


@pytest.mark.parametrize(
    "start,target",
    [
        (MissionStatus.QUEUED, MissionStatus.RUNNING),
        (MissionStatus.QUEUED, MissionStatus.CANCELLED),
        *[
            (MissionStatus.RUNNING, end)
            for end in (
                MissionStatus.COMPLETED,
                MissionStatus.PARTIAL,
                MissionStatus.FAILED,
                MissionStatus.CANCELLED,
            )
        ],
    ],
)
def test_valid_mission_transitions(
    mission: ResearchMission,
    start: MissionStatus,
    target: MissionStatus,
) -> None:
    before = replace(mission, status=start)
    after = before.transition(target, stage="test-stage")
    assert after.status is target
    assert before.status is start
    assert after.question == before.question
    assert after.stage == "test-stage"


@pytest.mark.parametrize(
    "start,target",
    [
        (start, target)
        for start in MissionStatus
        for target in MissionStatus
        if (start, target)
        not in {
            (MissionStatus.QUEUED, MissionStatus.RUNNING),
            (MissionStatus.QUEUED, MissionStatus.CANCELLED),
            (MissionStatus.RUNNING, MissionStatus.COMPLETED),
            (MissionStatus.RUNNING, MissionStatus.PARTIAL),
            (MissionStatus.RUNNING, MissionStatus.FAILED),
            (MissionStatus.RUNNING, MissionStatus.CANCELLED),
        }
    ],
)
def test_invalid_mission_transitions(
    mission: ResearchMission,
    start: MissionStatus,
    target: MissionStatus,
) -> None:
    with pytest.raises(InvalidStateTransition):
        replace(mission, status=start).transition(target)


def test_mission_inputs_are_frozen(mission: ResearchMission) -> None:
    with pytest.raises(FrozenInstanceError):
        mission.question = "Changed after start"  # type: ignore[misc]


def test_topic_association_is_explicit(mission: ResearchMission) -> None:
    first = ResearchTopic(id=mission.topic_id, owner_id=mission.owner_id, title="Energy")
    same_words = replace(first, id=TopicId(UUID(int=20)))
    assert first != same_words
    assert replace(mission, topic_id=same_words.id).question == mission.question


def test_first_result_becomes_current(mission: ResearchMission, result: ResearchResult) -> None:
    decision = plan_publication(mission, result)
    assert decision.is_new
    assert decision.current_brief is result
    assert decision.mission.status is MissionStatus.COMPLETED
    assert mission.status is MissionStatus.RUNNING


def test_newer_run_becomes_current_and_preserves_history(
    mission: ResearchMission,
    result: ResearchResult,
) -> None:
    newer_mission = replace(
        mission,
        id=MissionId(UUID(int=21)),
        run_sequence=2,
        baseline_result_id=result.id,
    )
    newer = replace(
        result,
        id=ResultId(UUID(int=22)),
        mission_id=newer_mission.id,
        run_sequence=2,
        baseline_result_id=result.id,
        version=2,
        answer="Updated findings",
    )
    decision = plan_publication(newer_mission, newer, current_brief=result)
    assert decision.current_brief is newer
    assert newer.baseline_result_id == result.id
    assert result.answer != newer.answer
    assert result.version == 1


def test_older_run_finishing_last_does_not_replace_newer_current(
    mission: ResearchMission,
    result: ResearchResult,
) -> None:
    run2 = replace(mission, id=MissionId(UUID(int=21)), run_sequence=2)
    completed_first = replace(
        result,
        id=ResultId(UUID(int=22)),
        mission_id=run2.id,
        run_sequence=2,
    )
    first = plan_publication(run2, completed_first)
    completed_later = replace(result, version=2)
    late = plan_publication(mission, completed_later, current_brief=first.current_brief)
    assert late.result.version == 2
    assert late.result.run_sequence == 1
    assert late.current_brief is completed_first
    assert late.is_new  # Historical publication is still valid.


@pytest.mark.parametrize(
    "status", [MissionStatus.FAILED, MissionStatus.CANCELLED, MissionStatus.QUEUED]
)
def test_unsuccessful_or_not_started_run_cannot_publish(
    mission: ResearchMission,
    result: ResearchResult,
    status: MissionStatus,
) -> None:
    with pytest.raises(InvalidResearchPublication):
        plan_publication(replace(mission, status=status), result)


def test_cancelled_mission_cannot_complete_or_publish(
    mission: ResearchMission,
    result: ResearchResult,
) -> None:
    cancelled = mission.transition(MissionStatus.CANCELLED)
    with pytest.raises(InvalidStateTransition):
        cancelled.transition(MissionStatus.COMPLETED)
    with pytest.raises(InvalidResearchPublication):
        plan_publication(cancelled, result)


def test_identical_publication_reuses_existing_result(
    mission: ResearchMission,
    result: ResearchResult,
) -> None:
    first = plan_publication(mission, result)
    retry = plan_publication(
        first.mission,
        result,
        existing_result=first.result,
        current_brief=first.current_brief,
    )
    assert not retry.is_new
    assert retry.result is first.result
    assert retry.current_brief is first.current_brief


def test_historical_publication_retry_does_not_change_current(
    mission: ResearchMission,
    result: ResearchResult,
) -> None:
    later = replace(
        result,
        id=ResultId(UUID(int=22)),
        mission_id=MissionId(UUID(int=21)),
        run_sequence=2,
        version=2,
    )
    retry = plan_publication(mission, result, existing_result=result, current_brief=later)
    assert not retry.is_new
    assert retry.current_brief is later


@pytest.mark.parametrize(
    "changes",
    [
        {"id": ResultId(UUID(int=99))},
        {"answer": "Overwritten"},
        {"version": 2},
    ],
)
def test_second_publication_input_cannot_overwrite_existing(
    mission: ResearchMission,
    result: ResearchResult,
    changes: dict[str, object],
) -> None:
    with pytest.raises(InvalidResearchPublication, match="overwrite"):
        plan_publication(mission, replace(result, **changes), existing_result=result)


@pytest.mark.parametrize(
    "changes",
    [
        {"owner_id": OwnerId(UUID(int=99))},
        {"topic_id": TopicId(UUID(int=99))},
        {"mission_id": MissionId(UUID(int=99))},
        {"run_sequence": 3},
        {"baseline_result_id": ResultId(UUID(int=99))},
    ],
)
def test_publication_must_match_frozen_mission(
    mission: ResearchMission,
    result: ResearchResult,
    changes: dict[str, object],
) -> None:
    # Owner mismatch uses a mission change so source ownership validation remains intact.
    bad_mission = replace(mission, **changes) if "owner_id" in changes else mission
    candidate = result if "owner_id" in changes else replace(result, **changes)
    with pytest.raises(InvalidResearchPublication, match="frozen mission"):
        plan_publication(bad_mission, candidate)


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner_id", OwnerId(UUID(int=99))),
        ("topic_id", TopicId(UUID(int=99))),
    ],
)
def test_current_brief_scope_must_match(
    mission: ResearchMission,
    result: ResearchResult,
    field: str,
    value: object,
) -> None:
    changed = replace(mission, **{field: value})
    evidence = tuple(replace(e, owner_id=changed.owner_id) for e in result.evidence)
    candidate = replace(
        result, owner_id=changed.owner_id, topic_id=changed.topic_id, evidence=evidence
    )
    with pytest.raises(InvalidResearchPublication, match="same owner and topic"):
        plan_publication(changed, candidate, current_brief=result)


def test_duplicate_run_sequence_across_missions_is_rejected(
    mission: ResearchMission,
    result: ResearchResult,
) -> None:
    other = replace(result, id=ResultId(UUID(int=23)), mission_id=MissionId(UUID(int=24)))
    with pytest.raises(InvalidResearchPublication, match="run sequence"):
        plan_publication(mission, result, current_brief=other)


def test_terminal_success_requires_existing_publication(
    mission: ResearchMission,
    result: ResearchResult,
) -> None:
    with pytest.raises(InvalidResearchPublication, match="stored publication"):
        plan_publication(mission.transition(MissionStatus.COMPLETED), result)


def test_partial_result_needs_limitations_and_yields_partial_mission(
    mission: ResearchMission,
    result: ResearchResult,
) -> None:
    with pytest.raises(InvalidResearchPublication, match="limitations"):
        replace(result, coverage=ResultCoverage.PARTIAL)
    partial = replace(result, coverage=ResultCoverage.PARTIAL, limitations=("One source failed",))
    decision = plan_publication(mission, partial)
    assert decision.mission.status is MissionStatus.PARTIAL


def test_published_result_and_nested_evidence_are_immutable(result: ResearchResult) -> None:
    with pytest.raises(FrozenInstanceError):
        result.answer = "Rewrite"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.evidence[0].quote = "Rewrite"  # type: ignore[misc]


def test_result_defensively_copies_evidence_and_limitations(result: ResearchResult) -> None:
    sources = list(result.evidence)
    limits = ["Pending refresh"]
    copied = replace(result, evidence=sources, limitations=limits)
    sources.clear()
    limits.clear()
    assert copied.evidence == result.evidence
    assert copied.limitations == ("Pending refresh",)


def test_empty_or_foreign_evidence_is_rejected(result: ResearchResult) -> None:
    with pytest.raises(MissingProvenance):
        replace(result, evidence=())
    with pytest.raises(MissingProvenance):
        replace(result, evidence=(replace(result.evidence[0], owner_id=OwnerId(UUID(int=99))),))


@pytest.mark.parametrize("field", ["version", "run_sequence"])
def test_positive_sequences_required(result: ResearchResult, field: str) -> None:
    with pytest.raises(DomainError):
        replace(result, **{field: 0})


def test_result_publication_timestamp_must_be_aware(result: ResearchResult) -> None:
    with pytest.raises(DomainError, match="timezone-aware"):
        replace(result, published_at=datetime(2026, 10, 21))


def test_publication_version_must_advance(
    mission: ResearchMission,
    result: ResearchResult,
) -> None:
    newer_mission = replace(mission, id=MissionId(UUID(int=21)), run_sequence=2)
    newer = replace(result, id=ResultId(UUID(int=22)), mission_id=newer_mission.id, run_sequence=2)
    with pytest.raises(InvalidResearchPublication, match="version must advance"):
        plan_publication(newer_mission, newer, current_brief=result)
