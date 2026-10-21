from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta, timezone
from uuid import UUID

import pytest

from lazyresearch.domain.actions import (
    ActionItem,
    ActionOrigin,
    ActionOriginType,
    ActionProposal,
    ActionStatus,
    Deadline,
)
from lazyresearch.domain.errors import (
    DomainError,
    InvalidStateTransition,
    MissingProvenance,
    RevisionConflict,
)
from lazyresearch.domain.identity import ActionId, OwnerId, ResultId


def test_action_with_evidence_retains_original_proposal(proposal: ActionProposal) -> None:
    task = ActionItem.from_proposal(ActionId(UUID(int=30)), proposal)
    assert task.status is ActionStatus.PROPOSED
    assert task.revision == 0
    assert task.proposal is proposal
    assert task.owner_id == proposal.owner_id


def test_research_action_still_requires_original_source(proposal: ActionProposal) -> None:
    research = replace(
        proposal,
        origin=ActionOrigin(
            kind=ActionOriginType.RESEARCH_RESULT,
            result_id=ResultId(UUID(int=31)),
        ),
    )
    assert research.evidence == proposal.evidence
    with pytest.raises(MissingProvenance):
        replace(research, evidence=())


def test_action_without_evidence_rejected(proposal: ActionProposal) -> None:
    with pytest.raises(MissingProvenance):
        replace(proposal, evidence=())


def test_foreign_owner_evidence_rejected(proposal: ActionProposal) -> None:
    with pytest.raises(MissingProvenance):
        replace(proposal, owner_id=OwnerId(UUID(int=99)))


@pytest.mark.parametrize("kind", list(ActionOriginType))
def test_missing_artifact_origin_is_rejected(kind: ActionOriginType) -> None:
    with pytest.raises(MissingProvenance):
        ActionOrigin(kind=kind)


def test_ambiguous_artifact_origin_rejected(proposal: ActionProposal) -> None:
    with pytest.raises(MissingProvenance):
        replace(proposal.origin, result_id=ResultId(UUID(int=99)))


@pytest.mark.parametrize(
    "start,target",
    [
        (ActionStatus.PROPOSED, ActionStatus.ACCEPTED),
        (ActionStatus.PROPOSED, ActionStatus.DISMISSED),
        (ActionStatus.ACCEPTED, ActionStatus.COMPLETED),
        (ActionStatus.ACCEPTED, ActionStatus.DISMISSED),
        (ActionStatus.COMPLETED, ActionStatus.ACCEPTED),
        (ActionStatus.DISMISSED, ActionStatus.ACCEPTED),
    ],
)
def test_action_valid_transitions_and_reopening(
    proposal: ActionProposal,
    start: ActionStatus,
    target: ActionStatus,
) -> None:
    task = replace(ActionItem.from_proposal(ActionId(UUID(int=30)), proposal), status=start)
    changed = task.transition(target, expected_revision=0)
    assert changed.status is target
    assert changed.revision == 1
    assert task.status is start
    assert changed.proposal is task.proposal


@pytest.mark.parametrize(
    "start,target",
    [
        (ActionStatus.PROPOSED, ActionStatus.COMPLETED),
        (ActionStatus.ACCEPTED, ActionStatus.PROPOSED),
        (ActionStatus.COMPLETED, ActionStatus.DISMISSED),
        (ActionStatus.COMPLETED, ActionStatus.PROPOSED),
        (ActionStatus.DISMISSED, ActionStatus.COMPLETED),
        (ActionStatus.DISMISSED, ActionStatus.PROPOSED),
        *[(state, state) for state in ActionStatus],
    ],
)
def test_action_invalid_transitions(
    proposal: ActionProposal,
    start: ActionStatus,
    target: ActionStatus,
) -> None:
    task = replace(ActionItem.from_proposal(ActionId(UUID(int=30)), proposal), status=start)
    with pytest.raises(InvalidStateTransition):
        task.transition(target, expected_revision=0)


def test_user_edits_do_not_change_proposal_or_evidence(proposal: ActionProposal) -> None:
    task = ActionItem.from_proposal(ActionId(UUID(int=30)), proposal)
    user_deadline = Deadline(normalized=date(2026, 10, 23))
    changed = task.edit(
        title="My reply",
        description="My notes",
        deadline=user_deadline,
        expected_revision=0,
    )
    assert changed.title == "My reply"
    assert changed.deadline == user_deadline
    assert changed.revision == 1
    assert changed.proposal is proposal
    assert proposal.title == task.title == "Reply"
    assert proposal.deadline.normalized is None
    with pytest.raises(FrozenInstanceError):
        changed.proposal.title = "Overwrite candidate"  # type: ignore[misc]


def test_stale_transition_and_edit_rejected(proposal: ActionProposal) -> None:
    task = ActionItem.from_proposal(ActionId(UUID(int=30)), proposal)
    accepted = task.transition(ActionStatus.ACCEPTED, expected_revision=0)
    with pytest.raises(RevisionConflict):
        accepted.transition(ActionStatus.COMPLETED, expected_revision=0)
    with pytest.raises(RevisionConflict):
        accepted.edit(title="Stale", description="Stale", deadline=Deadline(), expected_revision=0)


def test_user_can_clear_deadline_without_modifying_candidate(proposal: ActionProposal) -> None:
    original = replace(
        proposal, deadline=Deadline(raw_text="Friday", normalized=date(2026, 10, 23))
    )
    task = ActionItem.from_proposal(ActionId(UUID(int=30)), original)
    edited = task.edit(
        title=task.title,
        description=task.description,
        deadline=Deadline(),
        expected_revision=0,
    )
    assert edited.deadline.normalized is None
    assert edited.proposal.deadline.normalized == date(2026, 10, 23)


def test_deadline_uncertainty_does_not_invent_an_instant() -> None:
    unknown = Deadline(raw_text="next Friday evening")
    date_only = Deadline(raw_text="October 23", normalized=date(2026, 10, 23))
    assert unknown.normalized is None
    assert type(date_only.normalized) is date


def test_deadline_rejects_naive_datetime() -> None:
    with pytest.raises(DomainError, match="timezone-aware"):
        Deadline(normalized=datetime(2026, 10, 23, 18))


def test_deadline_normalizes_known_instant_to_utc() -> None:
    deadline = Deadline(normalized=datetime(2026, 10, 23, 18, tzinfo=timezone(timedelta(hours=2))))
    assert deadline.normalized == datetime(2026, 10, 23, 16, tzinfo=UTC)
    assert isinstance(deadline.normalized, datetime)
    assert deadline.normalized.tzinfo is UTC


def test_proposal_defensively_copies_evidence(proposal: ActionProposal) -> None:
    sources = list(proposal.evidence)
    copied = replace(proposal, evidence=sources)
    sources.clear()
    assert copied.evidence == proposal.evidence


def test_blank_user_edit_rejected(proposal: ActionProposal) -> None:
    task = ActionItem.from_proposal(ActionId(UUID(int=30)), proposal)
    with pytest.raises(DomainError, match="nonblank"):
        task.edit(title=" ", description="Keep", deadline=Deadline(), expected_revision=0)
