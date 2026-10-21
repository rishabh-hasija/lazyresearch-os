"""Short PostgreSQL transactions, owner-scoped values, and fenced processing leases."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import Engine, and_, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from lazyresearch.application.intake_models import (
    BatchResult,
    ContentExtraction,
    Disposition,
    EntryLease,
    EntryReceipt,
    EntryState,
    ErrorCode,
    ExtractionData,
    ExtractionStatus,
    FetchedSource,
    IntakeInput,
    IntakeLimits,
    PageSpan,
    ProcessingLease,
)
from lazyresearch.domain.content import CaptureOccurrence, ContentItem, SourceType
from lazyresearch.domain.identity import CaptureId, ContentId, OwnerId
from lazyresearch.infrastructure.persistence.models import (
    BatchRow,
    CaptureRow,
    ContentRow,
    EntryRow,
    ExtractionRow,
    JobRow,
    OwnerRow,
)
from lazyresearch.ports.errors import RepositoryConflict, RepositoryError


def source_key(snapshot: ContentItem) -> str:
    identity = snapshot.original_url or snapshot.source_external_id or ""
    return sha256(identity.encode("utf-8")).hexdigest()


def lock(session: Session, key: str) -> None:
    number = int.from_bytes(sha256(key.encode()).digest()[:8], "big", signed=True)
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": number})


def content_value(row: ContentRow) -> ContentItem:
    return ContentItem(
        id=ContentId(row.id),
        owner_id=OwnerId(row.owner_id),
        source_type=SourceType(row.source_type),
        raw_content=row.raw_content,
        raw_content_hash=row.raw_content_hash,
        captured_at=row.captured_at,
        original_title=row.original_title,
        author=row.author,
        original_url=row.original_url,
        canonical_url=row.canonical_url,
        source_external_id=row.source_external_id,
        published_at=row.published_at,
        predecessor_id=ContentId(row.predecessor_id) if row.predecessor_id else None,
    )


def content_row(
    snapshot: ContentItem, content_type: str, http_status: int | None = None
) -> ContentRow:
    return ContentRow(
        id=snapshot.id,
        owner_id=snapshot.owner_id,
        source_type=snapshot.source_type.value,
        source_key=source_key(snapshot),
        raw_content=snapshot.raw_content,
        raw_content_hash=snapshot.raw_content_hash,
        captured_at=snapshot.captured_at,
        original_title=snapshot.original_title,
        author=snapshot.author,
        original_url=snapshot.original_url,
        canonical_url=snapshot.canonical_url,
        source_external_id=snapshot.source_external_id,
        published_at=snapshot.published_at,
        predecessor_id=snapshot.predecessor_id,
        content_type=content_type,
        http_status=http_status,
    )


def capture_value(row: CaptureRow) -> CaptureOccurrence:
    return CaptureOccurrence(
        id=CaptureId(row.id),
        owner_id=OwnerId(row.owner_id),
        content_id=ContentId(row.content_id),
        captured_at=row.captured_at,
        intake_reference=row.intake_reference,
        submitted_url=row.submitted_url,
        submitted_filename=row.submitted_filename,
        final_url=row.final_url,
        content_type=row.content_type,
        http_status=row.http_status,
    )


class DatabaseAdapter:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        try:
            with Session(self.engine, expire_on_commit=False) as session, session.begin():
                yield session
        except IntegrityError as exc:
            raise RepositoryConflict("stored identity or ownership constraint conflict") from exc
        except SQLAlchemyError as exc:
            raise RepositoryError("database operation failed") from exc


class SQLAlchemyContentRepository(DatabaseAdapter):
    def get(self, owner_id: OwnerId, content_id: ContentId) -> ContentItem | None:
        with self.transaction() as s:
            row = s.scalar(
                select(ContentRow).where(
                    ContentRow.owner_id == owner_id, ContentRow.id == content_id
                )
            )
            return content_value(row) if row else None

    def save_capture(
        self, owner_id: OwnerId, snapshot: ContentItem, occurrence: CaptureOccurrence
    ) -> None:
        if (
            owner_id != snapshot.owner_id
            or owner_id != occurrence.owner_id
            or snapshot.id != occurrence.content_id
        ):
            raise RepositoryConflict("snapshot and occurrence scope must match")
        with self.transaction() as s:
            lock(s, f"capture:{owner_id}:{snapshot.id}")
            s.execute(insert(OwnerRow).values(id=owner_id).on_conflict_do_nothing())
            stored = s.get(ContentRow, snapshot.id)
            if stored is not None and content_value(stored) != snapshot:
                raise RepositoryConflict("immutable snapshot conflict")
            if stored is None:
                s.add(
                    content_row(
                        snapshot,
                        {
                            SourceType.PDF: "application/pdf",
                            SourceType.MARKDOWN: "text/markdown",
                        }.get(snapshot.source_type, "text/plain"),
                    )
                )
                s.flush()
            capture = s.get(CaptureRow, occurrence.id)
            if capture is not None:
                if capture_value(capture) != occurrence:
                    raise RepositoryConflict("immutable capture conflict")
                return
            s.add(
                CaptureRow(
                    id=occurrence.id,
                    owner_id=owner_id,
                    content_id=snapshot.id,
                    captured_at=occurrence.captured_at,
                    intake_reference=occurrence.intake_reference,
                    submitted_url=occurrence.submitted_url,
                    submitted_filename=occurrence.submitted_filename,
                    final_url=occurrence.final_url,
                    content_type=occurrence.content_type,
                    http_status=occurrence.http_status,
                )
            )


class SQLAlchemyIntakeStore(DatabaseAdapter):
    def __init__(
        self, engine: Engine, *, extraction_version: str, limits: IntakeLimits = IntakeLimits()
    ) -> None:
        super().__init__(engine)
        self.extraction_version = extraction_version
        self.limits = limits

    def create_batch(
        self,
        owner_id: OwnerId,
        request_key: str,
        entries: tuple[IntakeInput, ...],
        *,
        rejections: tuple[ErrorCode | None, ...] = (),
    ) -> UUID:
        if rejections and len(rejections) != len(entries):
            raise ValueError("every input must have a validation outcome")
        fingerprint = sha256(
            json.dumps(
                [
                    [
                        entry.source_type.value,
                        sha256(entry.payload).hexdigest() if entry.payload is not None else None,
                        entry.url,
                        entry.filename,
                        entry.content_type,
                        entry.title,
                    ]
                    for entry in entries
                ],
                ensure_ascii=True,
            ).encode()
        ).hexdigest()
        with self.transaction() as s:
            lock(s, f"batch:{owner_id}:{request_key}")
            existing = s.scalar(
                select(BatchRow).where(
                    BatchRow.owner_id == owner_id, BatchRow.request_key == request_key
                )
            )
            if existing:
                if existing.input_hash != fingerprint:
                    raise RepositoryConflict("request key reused with different inputs")
                return existing.id
            s.execute(insert(OwnerRow).values(id=owner_id).on_conflict_do_nothing())
            batch = BatchRow(owner_id=owner_id, request_key=request_key, input_hash=fingerprint)
            s.add(batch)
            s.flush()
            for ordinal, entry in enumerate(entries):
                oversized = (
                    entry.payload is not None and len(entry.payload) > self.limits.max_upload_bytes
                )
                rejection = rejections[ordinal] if rejections else None
                if oversized:
                    rejection = ErrorCode.FILE_TOO_LARGE
                s.add(
                    EntryRow(
                        owner_id=owner_id,
                        batch_id=batch.id,
                        ordinal=ordinal,
                        source_type=entry.source_type.value,
                        payload=None if rejection else entry.payload,
                        url=entry.url,
                        filename=entry.filename,
                        content_type=entry.content_type,
                        title=entry.title,
                        state="FAILED" if rejection else "QUEUED",
                        error_code=rejection.value if rejection else None,
                    )
                )
            return batch.id

    def batch(self, owner_id: OwnerId, batch_id: UUID) -> BatchResult:
        with self.transaction() as s:
            if (
                s.scalar(
                    select(BatchRow.id).where(
                        BatchRow.id == batch_id, BatchRow.owner_id == owner_id
                    )
                )
                is None
            ):
                raise RepositoryConflict("batch not available in owner scope")
            receipts = []
            rows = s.scalars(
                select(EntryRow)
                .where(EntryRow.batch_id == batch_id, EntryRow.owner_id == owner_id)
                .order_by(EntryRow.ordinal)
            )
            for row in rows:
                extraction = (
                    s.scalar(
                        select(ExtractionRow).where(
                            ExtractionRow.owner_id == owner_id,
                            ExtractionRow.content_id == row.content_id,
                            ExtractionRow.version == self.extraction_version,
                        )
                    )
                    if row.content_id
                    else None
                )
                disposition = (
                    (Disposition.DUPLICATE if row.duplicate else Disposition.SAVED)
                    if row.state == "SAVED"
                    else (Disposition.FAILED if row.state == "FAILED" else Disposition.PENDING)
                )
                code = extraction.error_code if extraction else row.error_code
                receipts.append(
                    EntryReceipt(
                        id=row.id,
                        source_type=SourceType(row.source_type),
                        state=EntryState(row.state),
                        disposition=disposition,
                        content_id=ContentId(row.content_id) if row.content_id else None,
                        extraction_status=ExtractionStatus(extraction.status)
                        if extraction
                        else ExtractionStatus.PENDING,
                        error_code=ErrorCode(code) if code else None,
                        http_status=row.http_status,
                    )
                )
            return BatchResult(batch_id=batch_id, entries=tuple(receipts))

    def claim_entry(
        self, owner_id: OwnerId, entry_id: UUID, *, retry_failed: bool = False
    ) -> EntryLease | None:
        with self.transaction() as s:
            claimable = or_(
                EntryRow.state == "QUEUED",
                and_(EntryRow.state == "FETCHING", EntryRow.lease_until <= func.clock_timestamp()),
            )
            if retry_failed:
                claimable = or_(
                    claimable,
                    and_(
                        EntryRow.state == "FAILED",
                        EntryRow.error_code.in_(
                            [
                                ErrorCode.FETCH_FAILED.value,
                                ErrorCode.FETCH_TIMEOUT.value,
                                ErrorCode.HTTP_ERROR.value,
                                ErrorCode.PERSISTENCE_ERROR.value,
                            ]
                        ),
                    ),
                )
            row = s.scalar(
                select(EntryRow)
                .where(EntryRow.id == entry_id, EntryRow.owner_id == owner_id, claimable)
                .with_for_update(skip_locked=True)
            )
            if row is None:
                return None
            now = s.scalar(select(func.clock_timestamp()))
            assert isinstance(now, datetime)
            row.state, row.lease_token = "FETCHING", uuid4()
            row.lease_until, row.error_code = (
                now + timedelta(seconds=self.limits.lease_seconds),
                None,
            )
            return EntryLease(
                entry_id=row.id,
                owner_id=owner_id,
                token=row.lease_token,
                input=IntakeInput(
                    source_type=SourceType(row.source_type),
                    payload=row.payload,
                    url=row.url,
                    filename=row.filename,
                    content_type=row.content_type,
                    title=row.title,
                ),
            )

    @staticmethod
    def _leased_entry(s: Session, lease: EntryLease) -> EntryRow:
        row = s.scalar(
            select(EntryRow)
            .where(
                EntryRow.owner_id == lease.owner_id,
                EntryRow.id == lease.entry_id,
                EntryRow.state == "FETCHING",
                EntryRow.lease_token == lease.token,
                EntryRow.lease_until > func.clock_timestamp(),
            )
            .with_for_update()
        )
        if row is None:
            raise RepositoryConflict("intake lease is no longer active")
        return row

    def save_original(self, lease: EntryLease, source: FetchedSource) -> ContentId:
        with self.transaction() as s:
            entry = self._leased_entry(s, lease)
            item = lease.input
            if item != IntakeInput(
                source_type=SourceType(entry.source_type),
                payload=entry.payload,
                url=entry.url,
                filename=entry.filename,
                content_type=entry.content_type,
                title=entry.title,
            ):
                raise RepositoryConflict("lease inputs differ from durable receipt")
            if item.source_type is not SourceType.URL and source.payload != item.payload:
                raise RepositoryConflict("local original differs from submitted bytes")
            snapshot = ContentItem(
                id=ContentId(uuid4()),
                owner_id=lease.owner_id,
                source_type=item.source_type,
                raw_content=source.payload,
                raw_content_hash=sha256(source.payload).hexdigest(),
                captured_at=source.fetched_at,
                original_title=item.title or item.filename,
                original_url=item.url,
                canonical_url=source.final_url or None,
            )
            key = source_key(snapshot)
            lock(s, f"source:{lease.owner_id}:{item.source_type.value}:{key}")
            identity = (
                ContentRow.owner_id == lease.owner_id,
                ContentRow.source_type == item.source_type.value,
                ContentRow.source_key == key,
            )
            row = s.scalar(
                select(ContentRow).where(
                    *identity, ContentRow.raw_content_hash == snapshot.raw_content_hash
                )
            )
            entry.duplicate = row is not None
            if row is None:
                previous = s.scalar(
                    select(ContentRow)
                    .join(
                        CaptureRow,
                        and_(
                            CaptureRow.content_id == ContentRow.id,
                            CaptureRow.owner_id == ContentRow.owner_id,
                        ),
                    )
                    .where(*identity)
                    .order_by(CaptureRow.recorded_at.desc(), CaptureRow.id.desc())
                    .limit(1)
                )
                row = content_row(snapshot, source.content_type, source.http_status or None)
                if item.source_type is SourceType.URL and previous is not None:
                    row.predecessor_id = previous.id
                s.add(row)
                s.flush()
            s.add(
                CaptureRow(
                    id=uuid4(),
                    owner_id=lease.owner_id,
                    content_id=row.id,
                    entry_id=entry.id,
                    captured_at=source.fetched_at,
                    intake_reference=str(entry.id),
                    submitted_url=item.url,
                    submitted_filename=item.filename,
                    final_url=source.final_url or None,
                    content_type=source.content_type,
                    http_status=source.http_status or None,
                )
            )
            s.execute(
                insert(JobRow)
                .values(
                    id=uuid4(),
                    owner_id=lease.owner_id,
                    content_id=row.id,
                    kind="EXTRACT",
                    version=self.extraction_version,
                    status="PENDING",
                    attempts=0,
                )
                .on_conflict_do_nothing(
                    index_elements=["owner_id", "content_id", "kind", "version"]
                )
            )
            entry.content_id, entry.state, entry.payload = row.id, "SAVED", None
            entry.http_status = source.http_status or None
            entry.lease_token, entry.lease_until = None, None
            return ContentId(row.id)

    def fail_entry(
        self, lease: EntryLease, code: ErrorCode, *, http_status: int | None = None
    ) -> None:
        with self.transaction() as s:
            row = self._leased_entry(s, lease)
            row.state, row.error_code = "FAILED", code.value
            row.http_status = http_status
            row.lease_token, row.lease_until = None, None

    def original(self, owner_id: OwnerId, content_id: ContentId) -> tuple[ContentItem, str]:
        with self.transaction() as s:
            row = s.scalar(
                select(ContentRow).where(
                    ContentRow.owner_id == owner_id, ContentRow.id == content_id
                )
            )
            if row is None:
                raise RepositoryConflict("content not available in owner scope")
            return content_value(row), row.content_type

    def extraction(self, owner_id: OwnerId, content_id: ContentId) -> ContentExtraction | None:
        with self.transaction() as s:
            row = s.scalar(
                select(ExtractionRow).where(
                    ExtractionRow.owner_id == owner_id,
                    ExtractionRow.content_id == content_id,
                    ExtractionRow.version == self.extraction_version,
                )
            )
            if row is None:
                return None
            return ContentExtraction(
                id=row.id,
                owner_id=owner_id,
                content_id=content_id,
                data=ExtractionData(
                    status=ExtractionStatus(row.status),
                    version=row.version,
                    text=row.text,
                    normalized_hash=row.normalized_hash,
                    pages=tuple(PageSpan(**p) for p in row.pages),
                    error_code=ErrorCode(row.error_code) if row.error_code else None,
                ),
            )

    def save_extraction(self, lease: ProcessingLease, data: ExtractionData) -> None:
        if lease.kind != "EXTRACT" or data.status is ExtractionStatus.PENDING:
            raise RepositoryConflict("only an extraction lease can save a final extraction")
        if data.status is ExtractionStatus.SUCCEEDED:
            if (
                not data.text.strip()
                or data.normalized_hash != sha256(data.text.encode()).hexdigest()
            ):
                raise RepositoryConflict("invalid normalized extraction hash")
        elif data.normalized_hash is not None or data.text:
            raise RepositoryConflict("unsuccessful extraction cannot contain generated text")
        if any(
            p.page < 1 or p.start < 0 or p.end < p.start or p.end > len(data.text)
            for p in data.pages
        ):
            raise RepositoryConflict("invalid page locators")
        with self.transaction() as s:
            job = SQLAlchemyProcessingRepository.leased_job(s, lease)
            if job.version != data.version:
                raise RepositoryConflict("extractor version changed during processing")
            row = ExtractionRow(
                id=uuid4(),
                owner_id=lease.owner_id,
                content_id=lease.content_id,
                version=data.version,
                status=data.status.value,
                text=data.text,
                normalized_hash=data.normalized_hash,
                pages=[{"page": p.page, "start": p.start, "end": p.end} for p in data.pages],
                error_code=data.error_code.value if data.error_code else None,
            )
            s.add(row)
            s.flush()
            job.status = "FAILED" if data.status is ExtractionStatus.FAILED else "SUCCEEDED"
            job.lease_token, job.lease_until = None, None
            if data.status is ExtractionStatus.SUCCEEDED:
                s.add(
                    JobRow(
                        owner_id=lease.owner_id,
                        content_id=lease.content_id,
                        extraction_id=row.id,
                        kind="ANALYZE",
                        version=data.version,
                        status="PENDING",
                        attempts=0,
                    )
                )


class SQLAlchemyProcessingRepository(DatabaseAdapter):
    def __init__(self, engine: Engine, *, lease_seconds: int = 90) -> None:
        super().__init__(engine)
        if lease_seconds <= 0:
            raise ValueError("lease must have positive duration")
        self.lease_seconds = lease_seconds

    def claim(
        self,
        owner_id: OwnerId,
        kind: str,
        *,
        content_id: ContentId | None = None,
        version: str | None = None,
    ) -> ProcessingLease | None:
        if kind not in {"EXTRACT", "ANALYZE"}:
            raise ValueError("unsupported processing kind")
        with self.transaction() as s:
            query = select(JobRow).where(
                JobRow.owner_id == owner_id,
                JobRow.kind == kind,
                or_(
                    JobRow.status == "PENDING",
                    and_(JobRow.status == "RUNNING", JobRow.lease_until <= func.clock_timestamp()),
                ),
            )
            if content_id is not None:
                query = query.where(JobRow.content_id == content_id)
            if version is not None:
                query = query.where(JobRow.version == version)
            row = s.scalar(
                query.order_by(JobRow.created_at, JobRow.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if row is None:
                return None
            now = s.scalar(select(func.clock_timestamp()))
            assert isinstance(now, datetime)
            row.status, row.lease_token = "RUNNING", uuid4()
            row.lease_until = now + timedelta(seconds=self.lease_seconds)
            row.attempts += 1
            return ProcessingLease(
                id=row.id,
                owner_id=owner_id,
                content_id=ContentId(row.content_id),
                extraction_id=row.extraction_id,
                kind=row.kind,
                version=row.version,
                token=row.lease_token,
                expires_at=row.lease_until,
            )

    @staticmethod
    def leased_job(s: Session, lease: ProcessingLease) -> JobRow:
        row = s.scalar(
            select(JobRow)
            .where(
                JobRow.id == lease.id,
                JobRow.owner_id == lease.owner_id,
                JobRow.content_id == lease.content_id,
                JobRow.kind == lease.kind,
                JobRow.version == lease.version,
                JobRow.extraction_id == lease.extraction_id,
                JobRow.status == "RUNNING",
                JobRow.lease_token == lease.token,
                JobRow.lease_until > func.clock_timestamp(),
            )
            .with_for_update()
        )
        if row is None:
            raise RepositoryConflict("processing lease expired or was replaced")
        return row

    def finish(self, lease: ProcessingLease) -> None:
        if lease.kind != "ANALYZE":
            raise RepositoryConflict("extraction completion requires its extraction outcome")
        with self.transaction() as s:
            row = self.leased_job(s, lease)
            row.status, row.lease_token, row.lease_until = "SUCCEEDED", None, None
