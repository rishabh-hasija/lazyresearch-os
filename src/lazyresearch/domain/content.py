"""Immutable captured originals, repeat captures, and version-specific source locators."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from hashlib import sha256

from lazyresearch.domain._validation import (
    require_count,
    require_id,
    require_sha256,
    require_text,
    utc_instant,
)
from lazyresearch.domain.errors import DomainError
from lazyresearch.domain.identity import CaptureId, ContentId, ExtractionId, OwnerId


class SourceType(StrEnum):
    URL = "URL"
    PDF = "PDF"
    TEXT = "TEXT"
    MARKDOWN = "MARKDOWN"


@dataclass(frozen=True, slots=True, kw_only=True)
class ContentItem:
    """One original snapshot, never an analysis or mutable latest-page container."""

    id: ContentId
    owner_id: OwnerId
    source_type: SourceType
    captured_at: datetime
    raw_content: bytes = field(repr=False)
    raw_content_hash: str
    original_title: str | None = None
    author: str | None = None
    original_url: str | None = None
    canonical_url: str | None = None
    source_external_id: str | None = None
    published_at: datetime | None = None
    predecessor_id: ContentId | None = None

    def __post_init__(self) -> None:
        require_id(self.id, "id")
        require_id(self.owner_id, "owner_id")
        if not isinstance(self.source_type, SourceType):
            raise DomainError("source_type must be SourceType")
        if not isinstance(self.raw_content, bytes):
            raise DomainError("raw_content must be immutable bytes")
        require_sha256(self.raw_content_hash, "raw_content_hash")
        if sha256(self.raw_content).hexdigest() != self.raw_content_hash:
            raise DomainError("raw_content_hash does not match original bytes")
        object.__setattr__(self, "captured_at", utc_instant(self.captured_at, "captured_at"))
        if self.published_at is not None:
            object.__setattr__(self, "published_at", utc_instant(self.published_at, "published_at"))
        if self.predecessor_id is not None:
            require_id(self.predecessor_id, "predecessor_id")
            if self.predecessor_id == self.id:
                raise DomainError("a snapshot cannot be its own predecessor")
        for name in (
            "original_title",
            "author",
            "original_url",
            "canonical_url",
            "source_external_id",
        ):
            value = getattr(self, name)
            if value is not None:
                require_text(value, name)
        if self.source_type is SourceType.URL and self.original_url is None:
            raise DomainError("URL snapshots require the original URL")


@dataclass(frozen=True, slots=True, kw_only=True)
class CaptureOccurrence:
    """A distinct intake occurrence may reference an already existing ContentItem."""

    id: CaptureId
    owner_id: OwnerId
    content_id: ContentId
    captured_at: datetime
    intake_reference: str
    submitted_url: str | None = None
    submitted_filename: str | None = None
    final_url: str | None = None
    content_type: str | None = None
    http_status: int | None = None

    def __post_init__(self) -> None:
        require_id(self.id, "id")
        require_id(self.owner_id, "owner_id")
        require_id(self.content_id, "content_id")
        require_text(self.intake_reference, "intake_reference")
        for name in ("submitted_url", "submitted_filename", "final_url", "content_type"):
            value = getattr(self, name)
            if value is not None:
                require_text(value, name)
        if self.http_status is not None:
            require_count(self.http_status, "http_status", minimum=100)
            if self.http_status > 599:
                raise DomainError("http_status must be between 100 and 599")
        object.__setattr__(self, "captured_at", utc_instant(self.captured_at, "captured_at"))


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceEvidence:
    """Reference to an immutable extraction, not a mutable URL or latest analysis.

    Offsets are a zero-based, half-open range of Unicode characters. Existence,
    ownership in storage, and quote support must be checked by a later adapter/use case.
    """

    owner_id: OwnerId
    content_id: ContentId
    extraction_id: ExtractionId
    start: int
    end: int
    quote: str = field(repr=False)
    page: int | None = None

    def __post_init__(self) -> None:
        require_id(self.owner_id, "owner_id")
        require_id(self.content_id, "content_id")
        require_id(self.extraction_id, "extraction_id")
        require_count(self.start, "start", minimum=0)
        require_count(self.end, "end")
        require_text(self.quote, "quote")
        if self.end <= self.start or self.end - self.start != len(self.quote):
            raise DomainError("evidence range must match quote length")
        if self.page is not None:
            require_count(self.page, "page")
