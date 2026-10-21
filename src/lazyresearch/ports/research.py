"""Domain lookup and transactional mission creation/publication contract."""

from typing import Protocol
from uuid import UUID

from lazyresearch.application.mission_models import MissionScope
from lazyresearch.domain.identity import MissionId, OwnerId, ResultId, TopicId
from lazyresearch.domain.research import ResearchMission, ResearchResult, ResearchTopic


class ResearchRepository(Protocol):
    """Scoped lookup and atomic publication; operational stage methods live in MissionStore."""

    def create_topic(
        self, owner: UUID, title: str, description: str | None = None
    ) -> ResearchTopic: ...

    def create_mission(
        self, owner: UUID, topic: UUID, question: str, scope: MissionScope
    ) -> ResearchMission: ...

    def publish(self, owner: UUID, mission: UUID) -> UUID: ...

    def versions(self, owner: UUID, topic: UUID) -> tuple[ResearchResult, ...]: ...

    def get_topic(self, owner_id: OwnerId, topic_id: TopicId) -> ResearchTopic | None: ...

    def get_mission(self, owner_id: OwnerId, mission_id: MissionId) -> ResearchMission | None: ...

    def get_result(self, owner_id: OwnerId, result_id: ResultId) -> ResearchResult | None: ...
