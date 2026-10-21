"""Snapshot/capture contract; batch ingestion and deduplication are not implemented."""

from typing import Protocol

from lazyresearch.domain.content import CaptureOccurrence, ContentItem
from lazyresearch.domain.identity import ContentId, OwnerId


class ContentRepository(Protocol):
    def get(self, owner_id: OwnerId, content_id: ContentId) -> ContentItem | None:
        """Return an authorized snapshot; missing or other-owner IDs both return None."""
        ...

    def save_capture(
        self,
        owner_id: OwnerId,
        snapshot: ContentItem,
        occurrence: CaptureOccurrence,
    ) -> None:
        """Atomically retain immutable snapshot and distinct capture occurrence.

        Verify matching owner/content IDs. Exact repeats by ID are no-ops;
        conflicting values under existing IDs raise RepositoryConflict.
        Never overwrite an original. Storage failures raise RepositoryError.
        Hash/source deduplication and intake receipts belong to the later slice.
        """
        ...
