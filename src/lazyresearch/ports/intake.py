"""Only contracts exercised by durable intake and extraction orchestration."""

from typing import Protocol
from uuid import UUID

from lazyresearch.application.intake_models import (
    BatchResult,
    ContentExtraction,
    EntryLease,
    ErrorCode,
    ExtractionData,
    FetchedSource,
    IntakeInput,
    ProcessingLease,
)
from lazyresearch.domain.content import ContentItem, SourceType
from lazyresearch.domain.identity import ContentId, OwnerId


class SourceFetcher(Protocol):
    def fetch(self, url: str) -> FetchedSource: ...


class TextExtractor(Protocol):
    @property
    def version(self) -> str: ...

    def extract(
        self, payload: bytes, source_type: SourceType, content_type: str
    ) -> ExtractionData: ...


class IntakeStore(Protocol):
    """All writes commit individually; storage failures become RepositoryError.

    Identity/scope conflicts become RepositoryConflict. No ORM values cross here.
    """

    def create_batch(
        self,
        owner_id: OwnerId,
        request_key: str,
        entries: tuple[IntakeInput, ...],
        *,
        rejections: tuple[ErrorCode | None, ...] = (),
    ) -> UUID: ...

    def batch(self, owner_id: OwnerId, batch_id: UUID) -> BatchResult: ...

    def claim_entry(
        self, owner_id: OwnerId, entry_id: UUID, *, retry_failed: bool = False
    ) -> EntryLease | None: ...

    def save_original(self, lease: EntryLease, source: FetchedSource) -> ContentId: ...

    def fail_entry(
        self, lease: EntryLease, code: ErrorCode, *, http_status: int | None = None
    ) -> None: ...

    def original(self, owner_id: OwnerId, content_id: ContentId) -> tuple[ContentItem, str]: ...

    def extraction(self, owner_id: OwnerId, content_id: ContentId) -> ContentExtraction | None: ...

    def save_extraction(self, lease: ProcessingLease, data: ExtractionData) -> None: ...


class ProcessingRepository(Protocol):
    def claim(
        self,
        owner_id: OwnerId,
        kind: str,
        *,
        content_id: ContentId | None = None,
        version: str | None = None,
    ) -> ProcessingLease | None: ...

    def finish(self, lease: ProcessingLease) -> None: ...
