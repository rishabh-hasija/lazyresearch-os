"""Immutable retrieval chunks always cite original extraction text."""

from dataclasses import dataclass, field
from hashlib import sha256
from uuid import UUID

from lazyresearch.domain._validation import require_count, require_id, require_text
from lazyresearch.domain.content import SourceEvidence
from lazyresearch.domain.errors import DomainError
from lazyresearch.domain.identity import ContentId, ExtractionId, OwnerId


@dataclass(frozen=True, slots=True, kw_only=True)
class ContentChunk:
    id: UUID
    owner_id: OwnerId
    content_id: ContentId
    extraction_id: UUID
    ordinal: int
    start: int
    end: int
    page: int | None
    text: str = field(repr=False)
    chunker_version: str
    text_hash: str

    def __post_init__(self) -> None:
        for name in ("id", "owner_id", "content_id", "extraction_id"):
            require_id(getattr(self, name), name)
        require_count(self.ordinal, "ordinal", minimum=0)
        require_text(self.chunker_version, "chunker_version")
        if sha256(self.text.encode()).hexdigest() != self.text_hash:
            raise DomainError("chunk text hash mismatch")
        _ = self.evidence  # Enforce the existing exact span invariants.

    @property
    def evidence(self) -> SourceEvidence:
        return SourceEvidence(
            owner_id=self.owner_id,
            content_id=self.content_id,
            extraction_id=ExtractionId(self.extraction_id),
            start=self.start,
            end=self.end,
            page=self.page,
            quote=self.text,
        )
