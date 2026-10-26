"""Application-shaped source analysis and atomic publication contracts."""

from typing import Protocol

from lazyresearch.application.analysis_models import (
    AIResult,
    AnalysisConfig,
    AnalysisRequest,
    AnalysisWork,
    CallAttempt,
)
from lazyresearch.domain.analysis import ContentAnalysis
from lazyresearch.domain.identity import OwnerId


class AIProcessor(Protocol):
    def analyze(self, request: AnalysisRequest) -> AIResult:
        """Return validated output or sanitized AIError; at most one structural repair."""
        ...


class AnalysisStore(Protocol):
    def claim(self, owner_id: OwnerId, config: AnalysisConfig) -> AnalysisWork | None: ...
    def pending_sources(self, owner_id: OwnerId, config: AnalysisConfig) -> int: ...
    def renew(self, work: AnalysisWork) -> None: ...
    def publish(
        self, work: AnalysisWork, analysis: ContentAnalysis, attempts: tuple[CallAttempt, ...]
    ) -> None: ...
    def fail(self, work: AnalysisWork, error: str, attempts: tuple[CallAttempt, ...]) -> None: ...
