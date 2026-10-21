"""Narrow intake values; raw originals and extraction outputs remain separate."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from math import isfinite
from uuid import UUID

from lazyresearch.domain.content import SourceType
from lazyresearch.domain.identity import ContentId, OwnerId


class ErrorCode(StrEnum):
    INVALID_URL = "INVALID_URL"
    UNSUPPORTED_SCHEME = "UNSUPPORTED_SCHEME"
    PRIVATE_NETWORK_BLOCKED = "PRIVATE_NETWORK_BLOCKED"
    FETCH_TIMEOUT = "FETCH_TIMEOUT"
    FETCH_TOO_LARGE = "FETCH_TOO_LARGE"
    FETCH_FAILED = "FETCH_FAILED"
    HTTP_ERROR = "HTTP_ERROR"
    UNSUPPORTED_FILE = "UNSUPPORTED_FILE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    PDF_ENCRYPTED = "PDF_ENCRYPTED"
    PDF_TEXT_UNAVAILABLE = "PDF_TEXT_UNAVAILABLE"
    PDF_INVALID = "PDF_INVALID"
    PDF_TOO_MANY_PAGES = "PDF_TOO_MANY_PAGES"
    EXTRACTION_TIMEOUT = "EXTRACTION_TIMEOUT"
    EXTRACTION_TOO_LARGE = "EXTRACTION_TOO_LARGE"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    TEXT_UNAVAILABLE = "TEXT_UNAVAILABLE"
    DECODE_FAILED = "DECODE_FAILED"
    PERSISTENCE_ERROR = "PERSISTENCE_ERROR"


class SourceError(Exception):
    """Sanitized category; never expose arbitrary underlying exception text."""

    def __init__(self, code: ErrorCode, *, http_status: int | None = None) -> None:
        self.code = code
        self.http_status = http_status
        super().__init__(code.value)


class EntryState(StrEnum):
    QUEUED = "QUEUED"
    FETCHING = "FETCHING"
    SAVED = "SAVED"
    FAILED = "FAILED"


class Disposition(StrEnum):
    PENDING = "PENDING"
    SAVED = "SAVED"
    DUPLICATE = "DUPLICATE"
    FAILED = "FAILED"


class ExtractionStatus(StrEnum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True, kw_only=True)
class IntakeLimits:
    max_upload_bytes: int = 10 * 1024 * 1024
    max_fetch_bytes: int = 10 * 1024 * 1024
    fetch_timeout_seconds: float = 30
    connect_timeout_seconds: float = 5
    read_timeout_seconds: float = 5
    max_redirects: int = 5
    max_batch_entries: int = 20
    max_pdf_pages: int = 200
    extraction_timeout_seconds: float = 15
    max_extracted_chars: int = 2_000_000
    lease_seconds: int = 90

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
            ):
                raise ValueError(f"{name} must be finite numeric configuration")
            if "timeout" not in name and type(value) is not int:
                raise ValueError(f"{name} must be an integer")
            if value < 0 or (name != "max_redirects" and value == 0):
                raise ValueError(f"{name} must be positive (redirects may be zero)")


@dataclass(frozen=True, slots=True, kw_only=True)
class IntakeInput:
    source_type: SourceType
    payload: bytes | None = field(default=None, repr=False)
    url: str | None = field(default=None, repr=False)
    filename: str | None = None
    content_type: str | None = None
    title: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_type, SourceType):
            raise ValueError("source_type must be SourceType")
        if self.payload is not None and not isinstance(self.payload, bytes):
            raise ValueError("input payload must be immutable bytes")
        for value in (self.url, self.filename, self.content_type, self.title):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError("input metadata must be nonblank text when supplied")


@dataclass(frozen=True, slots=True, kw_only=True)
class FetchedSource:
    payload: bytes = field(repr=False)
    final_url: str
    fetched_at: datetime
    http_status: int
    content_type: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PageSpan:
    page: int
    start: int
    end: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ExtractionData:
    status: ExtractionStatus
    version: str
    text: str = field(default="", repr=False)
    normalized_hash: str | None = None
    pages: tuple[PageSpan, ...] = ()
    error_code: ErrorCode | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ContentExtraction:
    id: UUID
    owner_id: OwnerId
    content_id: ContentId
    data: ExtractionData


@dataclass(frozen=True, slots=True, kw_only=True)
class EntryReceipt:
    id: UUID
    source_type: SourceType
    state: EntryState
    disposition: Disposition
    content_id: ContentId | None = None
    extraction_status: ExtractionStatus = ExtractionStatus.PENDING
    error_code: ErrorCode | None = None
    http_status: int | None = None

    @property
    def message(self) -> str | None:
        if self.error_code is None:
            return None
        return {
            ErrorCode.PDF_TEXT_UNAVAILABLE: "Original saved; no text found. OCR may be required.",
            ErrorCode.PDF_ENCRYPTED: "Original saved; encrypted PDF cannot be extracted.",
        }.get(self.error_code, self.error_code.value.replace("_", " ").capitalize() + ".")


@dataclass(frozen=True, slots=True, kw_only=True)
class BatchResult:
    batch_id: UUID
    entries: tuple[EntryReceipt, ...]

    @property
    def total(self) -> int:
        return len(self.entries)

    @property
    def saved(self) -> int:
        return sum(e.disposition is Disposition.SAVED for e in self.entries)

    @property
    def duplicate(self) -> int:
        return sum(e.disposition is Disposition.DUPLICATE for e in self.entries)

    @property
    def failed(self) -> int:
        return sum(e.disposition is Disposition.FAILED for e in self.entries)

    @property
    def pending(self) -> int:
        return sum(e.disposition is Disposition.PENDING for e in self.entries)

    @property
    def extraction_pending(self) -> int:
        return sum(
            e.content_id is not None and e.extraction_status is ExtractionStatus.PENDING
            for e in self.entries
        )

    @property
    def extraction_unavailable(self) -> int:
        return sum(
            e.content_id is not None and e.extraction_status is ExtractionStatus.UNAVAILABLE
            for e in self.entries
        )

    @property
    def extraction_failed(self) -> int:
        return sum(
            e.content_id is not None and e.extraction_status is ExtractionStatus.FAILED
            for e in self.entries
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class EntryLease:
    entry_id: UUID
    owner_id: OwnerId
    token: UUID
    input: IntakeInput


@dataclass(frozen=True, slots=True, kw_only=True)
class ProcessingLease:
    id: UUID
    owner_id: OwnerId
    content_id: ContentId
    extraction_id: UUID | None
    kind: str
    version: str
    token: UUID
    expires_at: datetime
