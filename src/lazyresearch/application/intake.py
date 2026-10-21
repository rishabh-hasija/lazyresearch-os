"""Persist originals before extraction; errors are isolated to an intake entry."""

from datetime import UTC, datetime
from pathlib import PurePath
from uuid import UUID

from lazyresearch.application.intake_models import (
    BatchResult,
    ErrorCode,
    FetchedSource,
    IntakeInput,
    IntakeLimits,
    SourceError,
)
from lazyresearch.domain.content import SourceType
from lazyresearch.domain.identity import ContentId, OwnerId
from lazyresearch.ports.errors import RepositoryConflict, RepositoryError
from lazyresearch.ports.intake import (
    IntakeStore,
    ProcessingRepository,
    SourceFetcher,
    TextExtractor,
)


class IntakeService:
    def __init__(
        self,
        store: IntakeStore,
        jobs: ProcessingRepository,
        fetcher: SourceFetcher,
        extractor: TextExtractor,
        limits: IntakeLimits = IntakeLimits(),
    ) -> None:
        self.store, self.jobs, self.fetcher, self.extractor = store, jobs, fetcher, extractor
        self.limits = limits

    def ingest(
        self, owner_id: OwnerId, request_key: str, entries: tuple[IntakeInput, ...]
    ) -> BatchResult:
        if not request_key.strip() or not 1 <= len(entries) <= self.limits.max_batch_entries:
            raise ValueError("a request key and a bounded nonempty batch are required")
        rejections: list[ErrorCode | None] = []
        for item in entries:
            try:
                if item.source_type is not SourceType.URL:
                    self._validate_local(item)
                elif not item.url or item.payload is not None:
                    raise SourceError(ErrorCode.INVALID_URL)
                rejections.append(None)
            except SourceError as exc:
                rejections.append(exc.code)
        batch_id = self.store.create_batch(
            owner_id, request_key, entries, rejections=tuple(rejections)
        )
        return self.resume(owner_id, batch_id)

    def resume(
        self, owner_id: OwnerId, batch_id: UUID, *, retry_failed: bool = False
    ) -> BatchResult:
        for receipt in self.store.batch(owner_id, batch_id).entries:
            lease = self.store.claim_entry(owner_id, receipt.id, retry_failed=retry_failed)
            content_id = receipt.content_id
            if lease is not None:
                try:
                    item = lease.input
                    if item.source_type is SourceType.URL:
                        if not item.url or item.payload is not None:
                            raise SourceError(ErrorCode.INVALID_URL)
                        source = self.fetcher.fetch(item.url)
                    else:
                        self._validate_local(item)
                        assert item.payload is not None
                        source = FetchedSource(
                            payload=item.payload,
                            final_url="",
                            fetched_at=datetime.now(UTC),
                            http_status=0,
                            content_type=item.content_type or self._media(item.source_type),
                        )
                    content_id = self.store.save_original(lease, source)
                except SourceError as exc:
                    try:
                        self.store.fail_entry(lease, exc.code, http_status=exc.http_status)
                    except RepositoryError:
                        pass  # Persisted lease permits recovery after a storage outage.
                    continue
                except RepositoryConflict:
                    continue  # Another lease holder recovered this entry; never overwrite it.
                except RepositoryError:
                    try:
                        self.store.fail_entry(lease, ErrorCode.PERSISTENCE_ERROR)
                    except RepositoryError:
                        pass
                    continue
            if content_id is not None:
                try:
                    self.extract_saved(owner_id, content_id)
                except (RepositoryError, SourceError):
                    continue  # Original and extraction job are already durable.
        return self.store.batch(owner_id, batch_id)

    def extract_saved(self, owner_id: OwnerId, content_id: ContentId) -> bool:
        lease = self.jobs.claim(
            owner_id, "EXTRACT", content_id=content_id, version=self.extractor.version
        )
        if lease is None:
            return False
        snapshot, content_type = self.store.original(owner_id, content_id)
        data = self.extractor.extract(snapshot.raw_content, snapshot.source_type, content_type)
        self.store.save_extraction(lease, data)
        return True

    def _validate_local(self, item: IntakeInput) -> None:
        if item.payload is None or item.url is not None:
            raise SourceError(ErrorCode.UNSUPPORTED_FILE)
        if len(item.payload) > self.limits.max_upload_bytes:
            raise SourceError(ErrorCode.FILE_TOO_LARGE)
        suffix = PurePath(item.filename).suffix.lower() if item.filename else None
        media = (item.content_type or self._media(item.source_type)).split(";")[0].lower().strip()
        allowed = {
            SourceType.TEXT: ({".txt"}, {"text/plain"}),
            SourceType.MARKDOWN: ({".md", ".markdown"}, {"text/markdown", "text/plain"}),
            SourceType.PDF: ({".pdf"}, {"application/pdf"}),
        }
        if item.source_type not in allowed:
            raise SourceError(ErrorCode.UNSUPPORTED_FILE)
        extensions, types = allowed[item.source_type]
        if (suffix is not None and suffix not in extensions) or media not in types:
            raise SourceError(ErrorCode.UNSUPPORTED_FILE)
        if item.source_type is SourceType.PDF and not item.payload.startswith(b"%PDF-"):
            raise SourceError(ErrorCode.UNSUPPORTED_FILE)

    @staticmethod
    def _media(source_type: SourceType) -> str:
        return {SourceType.PDF: "application/pdf", SourceType.MARKDOWN: "text/markdown"}.get(
            source_type, "text/plain"
        )
