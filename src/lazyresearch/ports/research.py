"""Reference lookup only: transactional publication is deliberately deferred."""

from typing import Protocol

from lazyresearch.domain.identity import MissionId, OwnerId, ResultId, TopicId
from lazyresearch.domain.research import ResearchMission, ResearchResult, ResearchTopic


class ResearchRepository(Protocol):
    """Missing/other-owner lookups return None; storage failures raise RepositoryError.

    Publication requires locked reads, version allocation and atomic writes. Its
    port will be introduced with that use case, rather than exposing an unsafe
    save(result) method or pretending a pure decision is a transaction receipt.
    """

    def get_topic(self, owner_id: OwnerId, topic_id: TopicId) -> ResearchTopic | None: ...

    def get_mission(self, owner_id: OwnerId, mission_id: MissionId) -> ResearchMission | None: ...

    def get_result(self, owner_id: OwnerId, result_id: ResultId) -> ResearchResult | None: ...
