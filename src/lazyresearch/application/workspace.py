"""Application-facing façade. Mutations are explicit, bounded and owner scoped."""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from lazyresearch.application.analysis import ProcessPendingContent
from lazyresearch.application.intake import IntakeService
from lazyresearch.application.intake_models import BatchResult, IntakeInput
from lazyresearch.application.mission_models import MissionScope
from lazyresearch.application.relevance import CatchUp
from lazyresearch.application.relevance_models import InteractionKind, RankingDecision, Relevance
from lazyresearch.domain.actions import ActionItem, ActionStatus, Deadline
from lazyresearch.domain.content import SourceType
from lazyresearch.domain.identity import ActionId, ContentId, OwnerId
from lazyresearch.ports.actions import ActionRepository
from lazyresearch.ports.errors import RepositoryConflict
from lazyresearch.ports.workspace import MissionCommands, WorkspaceReads


class Workspace:
    def __init__(
        self,
        owner: OwnerId,
        reads: WorkspaceReads,
        intake: IntakeService,
        ranking: CatchUp,
        tasks: ActionRepository,
        missions: MissionCommands,
        processing: Callable[[], ProcessPendingContent],
        index: Callable[[OwnerId], int],
        scope: MissionScope,
        *,
        public_available: bool,
    ) -> None:
        self.owner, self.reads, self.intake, self.ranking = owner, reads, intake, ranking
        self.tasks, self.mission_commands = tasks, missions
        self.processing, self.index, self.scope = processing, index, scope
        self.public_available = public_available
        self.research_health: Callable[[], bool] | None = None

    def add(
        self, key: str, entries: tuple[IntakeInput, ...], *, collection: UUID | None = None
    ) -> BatchResult:
        if collection and collection not in {
            identity for identity, _ in self.reads.collections(self.owner)
        }:
            raise RepositoryConflict("collection unavailable")
        receipt = self.intake.ingest(self.owner, key, entries)
        if collection:
            for entry in receipt.entries:
                if entry.content_id:
                    self.reads.assign_collection(self.owner, collection, entry.content_id)
        return receipt

    def load_demo(self) -> BatchResult:
        return self.add(
            "ui-synthetic-demo-v1",
            (
                IntakeInput(
                    source_type=SourceType.TEXT,
                    title="Synthetic battery installer quote",
                    payload=(
                        b"Synthetic demo only. Battery quote EUR 6000 for 10 kWh. "
                        b"Request an installer assessment by 2026-11-07."
                    ),
                ),
                IntakeInput(
                    source_type=SourceType.TEXT,
                    title="Synthetic battery research notes",
                    payload=(
                        b"Synthetic demo only. Battery electricity rate is EUR 0.30 per kWh. "
                        b"Compare battery quotes and warranty terms before deciding."
                    ),
                ),
            ),
        )

    def process(self) -> str:
        outcome = self.processing().process_one(self.owner)
        return outcome.status if not outcome.error_code else "FAILED:" + outcome.error_code

    def catch_up(self, interests: tuple[str, ...] = ()) -> tuple[RankingDecision, ...]:
        return self.ranking.rank(self.owner, datetime.now(UTC), interests=interests)

    def reviewed(self, content: UUID, interests: tuple[str, ...] = ()) -> RankingDecision | None:
        decisions = self.ranking.rank(
            self.owner, datetime.now(UTC), interests=interests, content_id=ContentId(content)
        )
        return decisions[0] if decisions else None

    def feedback(
        self,
        decision: RankingDecision,
        label: Relevance,
        *,
        expected_event: UUID | None = None,
    ) -> UUID:
        if decision.item.owner_id != self.owner:
            raise RepositoryConflict("ranking unavailable")
        event = uuid4()
        self.ranking.store.interact(
            self.owner,
            ContentId(decision.item.content_id),
            event,
            InteractionKind.FEEDBACK_LABELED,
            datetime.now(UTC),
            explicit=True,
            observation_id=decision.id,
            label=label,
            supersedes=expected_event,
        )
        return event

    def research(
        self, topic: UUID, question: str, *, public: bool, collections: tuple[UUID, ...] = ()
    ) -> UUID:
        # Indexing is explicit work at submission, never hidden in read-only retrieval.
        self.index(self.owner)
        scope = self.scope.model_copy(update={"public": public, "collection_ids": collections})
        mission = self.mission_commands.create_mission(self.owner, topic, question, scope)
        return mission.id

    def cancel(self, mission: UUID) -> None:
        # The persisted terminal fence is authoritative; the worker sees cancellation.
        self.mission_commands.terminal(self.owner, mission, "CANCELLED", "CANCELLED")

    def actions(self) -> tuple[ActionItem, ...]:
        result = []
        for proposal in self.reads.proposals(self.owner):
            identity = ActionId(uuid5(NAMESPACE_URL, f"action:{self.owner}:{proposal.id}"))
            result.append(
                self.tasks.get(self.owner, identity) or ActionItem.from_proposal(identity, proposal)
            )
        return tuple(result)

    def change_action(
        self,
        item: ActionItem,
        target: ActionStatus | None = None,
        *,
        title: str | None = None,
        description: str | None = None,
        deadline: Deadline | None = None,
    ) -> None:
        if item.owner_id != self.owner:
            raise RepositoryConflict("action unavailable")
        if self.tasks.get(self.owner, item.id) is None:
            self.tasks.save(
                self.owner, ActionItem.from_proposal(item.id, item.proposal), expected_revision=None
            )
        if target is not None:
            changed = item.transition(target, expected_revision=item.revision)
        else:
            changed = item.edit(
                title=title if title is not None else item.title,
                description=description if description is not None else item.description,
                deadline=deadline if deadline is not None else item.deadline,
                expected_revision=item.revision,
            )
        self.tasks.save(self.owner, changed, expected_revision=item.revision)
