from dataclasses import replace
from io import BytesIO
from uuid import uuid4

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from lazyresearch.application.intake import IntakeService
from lazyresearch.application.intake_models import ErrorCode, ExtractionStatus, IntakeInput
from lazyresearch.domain.content import SourceType
from lazyresearch.domain.identity import OwnerId
from lazyresearch.infrastructure.persistence.models import ContentRow
from lazyresearch.infrastructure.persistence.repositories import SQLAlchemyIntakeStore

pytestmark = pytest.mark.integration


def pdf_bytes(*, encrypted: bool = False, empty: bool = False) -> bytes:
    writer = PdfWriter()
    for number in range(1, 3):
        page = writer.add_blank_page(width=612, height=792)
        if not empty:
            font = DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Font"),
                    NameObject("/Subtype"): NameObject("/Type1"),
                    NameObject("/BaseFont"): NameObject("/Helvetica"),
                }
            )
            page[NameObject("/Resources")] = DictionaryObject(
                {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
            )
            stream = DecodedStreamObject()
            stream.set_data(f"BT /F1 12 Tf 72 720 Td (Synthetic page {number}) Tj ET".encode())
            page[NameObject("/Contents")] = stream
    if encrypted:
        writer.encrypt("synthetic-password")
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def test_text_pdf_preserves_pages_and_original(
    service: IntakeService,
    store: SQLAlchemyIntakeStore,
) -> None:
    owner = OwnerId(uuid4())
    raw = pdf_bytes()
    result = service.ingest(
        owner, "pdf", (IntakeInput(source_type=SourceType.PDF, payload=raw, filename="paper.pdf"),)
    )
    assert result.saved == 1
    assert result.entries[0].extraction_status is ExtractionStatus.SUCCEEDED
    content_id = result.entries[0].content_id
    assert store.original(owner, content_id)[0].raw_content == raw
    extraction = store.extraction(owner, content_id)
    assert extraction is not None
    assert len(extraction.data.pages) == 2
    for span in extraction.data.pages:
        assert f"Synthetic page {span.page}" in extraction.data.text[span.start : span.end]


@pytest.mark.parametrize(
    "encrypted,empty,code,status",
    [
        (True, False, ErrorCode.PDF_ENCRYPTED, ExtractionStatus.FAILED),
        (False, True, ErrorCode.PDF_TEXT_UNAVAILABLE, ExtractionStatus.UNAVAILABLE),
    ],
)
def test_unextractable_pdf_remains_saved(
    db: Engine,
    service: IntakeService,
    encrypted: bool,
    empty: bool,
    code: ErrorCode,
    status: ExtractionStatus,
) -> None:
    result = service.ingest(
        OwnerId(uuid4()),
        "pdf",
        (
            IntakeInput(
                source_type=SourceType.PDF,
                payload=pdf_bytes(encrypted=encrypted, empty=empty),
                filename="a.pdf",
            ),
        ),
    )
    assert result.saved == 1 and result.failed == 0
    assert result.entries[0].error_code is code
    assert result.entries[0].extraction_status is status
    assert result.entries[0].message.startswith("Original saved")
    with Session(db) as s:
        assert s.scalar(select(func.count()).select_from(ContentRow)) == 1


def test_invalid_pdf_signature_is_rejected_before_snapshot(service: IntakeService) -> None:
    result = service.ingest(
        OwnerId(uuid4()),
        "invalid",
        (
            IntakeInput(
                source_type=SourceType.PDF,
                payload=b"not PDF",
                filename="a.pdf",
            ),
        ),
    )
    assert result.failed == 1 and result.saved == 0
    assert result.entries[0].error_code is ErrorCode.UNSUPPORTED_FILE


@pytest.mark.parametrize(
    "limits,code",
    [
        ({"max_pdf_pages": 1}, ErrorCode.PDF_TOO_MANY_PAGES),
        ({"extraction_timeout_seconds": 0.001}, ErrorCode.EXTRACTION_TIMEOUT),
        ({"max_extracted_chars": 2}, ErrorCode.EXTRACTION_TOO_LARGE),
    ],
)
def test_pdf_extraction_bounds_keep_original(service: IntakeService, limits, code) -> None:
    service.extractor.limits = replace(service.limits, **limits)
    result = service.ingest(
        OwnerId(uuid4()),
        "bounded",
        (
            IntakeInput(
                source_type=SourceType.PDF,
                payload=pdf_bytes(),
                filename="a.pdf",
            ),
        ),
    )
    assert result.saved == 1 and result.failed == 0
    assert result.entries[0].error_code is code


def test_malformed_pdf_keeps_durable_original(service: IntakeService) -> None:
    result = service.ingest(
        OwnerId(uuid4()),
        "broken",
        (
            IntakeInput(
                source_type=SourceType.PDF,
                payload=b"%PDF-1.7\nbroken",
                filename="a.pdf",
            ),
        ),
    )
    assert result.saved == 1 and result.extraction_failed == 1
    assert result.entries[0].error_code is ErrorCode.PDF_INVALID
