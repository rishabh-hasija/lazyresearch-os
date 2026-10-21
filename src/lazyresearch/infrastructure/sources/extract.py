"""Conservative text extraction; PDFs run in a time-bounded child process."""

import logging
import multiprocessing
from hashlib import sha256
from html.parser import HTMLParser
from io import BytesIO
from multiprocessing.connection import Connection

from pypdf import PdfReader
from pypdf import __version__ as PDF_LIBRARY_VERSION

from lazyresearch.application.intake_models import (
    ErrorCode,
    ExtractionData,
    ExtractionStatus,
    IntakeLimits,
    PageSpan,
)
from lazyresearch.domain.content import SourceType


def normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def success(text: str, version: str, pages: tuple[PageSpan, ...] = ()) -> ExtractionData:
    return ExtractionData(
        status=ExtractionStatus.SUCCEEDED,
        version=version,
        text=text,
        normalized_hash=sha256(text.encode("utf-8")).hexdigest(),
        pages=pages,
    )


class HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "head"}:
            self.hidden += 1
        if not self.hidden and tag in {"p", "div", "br", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "head"} and self.hidden:
            self.hidden -= 1
        if not self.hidden and tag in {"p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def _pdf_worker(raw: bytes, limits: IntakeLimits, version: str, output: Connection) -> None:
    logger = logging.getLogger("pypdf")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    try:
        reader = PdfReader(BytesIO(raw), strict=True)
        if reader.is_encrypted:
            data = ExtractionData(
                status=ExtractionStatus.FAILED, version=version, error_code=ErrorCode.PDF_ENCRYPTED
            )
        elif len(reader.pages) > limits.max_pdf_pages:
            data = ExtractionData(
                status=ExtractionStatus.FAILED,
                version=version,
                error_code=ErrorCode.PDF_TOO_MANY_PAGES,
            )
        else:
            parts: list[str] = []
            spans: list[PageSpan] = []
            offset = 0
            for index, page in enumerate(reader.pages, 1):
                stream = page.get_contents()
                if stream is not None and len(stream.get_data()) > 5 * 1024 * 1024:
                    raise OverflowError
                text = normalize(page.extract_text() or "")
                if "\x00" in text:
                    raise ValueError("invalid text encoding")
                if offset + len(text) > limits.max_extracted_chars:
                    raise OverflowError
                spans.append(PageSpan(page=index, start=offset, end=offset + len(text)))
                parts.append(text)
                offset += len(text)
                if index < len(reader.pages):
                    parts.append("\n")
                    offset += 1
            joined = "".join(parts)
            data = (
                success(joined, version, tuple(spans))
                if joined.strip()
                else ExtractionData(
                    status=ExtractionStatus.UNAVAILABLE,
                    version=version,
                    error_code=ErrorCode.PDF_TEXT_UNAVAILABLE,
                )
            )
        output.send(data)
    except OverflowError:
        output.send(
            ExtractionData(
                status=ExtractionStatus.FAILED,
                version=version,
                error_code=ErrorCode.EXTRACTION_TOO_LARGE,
            )
        )
    except Exception:
        output.send(
            ExtractionData(
                status=ExtractionStatus.FAILED, version=version, error_code=ErrorCode.PDF_INVALID
            )
        )
    finally:
        output.close()


class SourceTextExtractor:
    version = f"text-v1-pypdf-{PDF_LIBRARY_VERSION}"

    def __init__(self, limits: IntakeLimits = IntakeLimits()) -> None:
        self.limits = limits

    def extract(self, payload: bytes, source_type: SourceType, content_type: str) -> ExtractionData:
        if (
            source_type is SourceType.PDF
            or content_type.split(";")[0].strip().lower() == "application/pdf"
        ):
            return self._pdf(payload)
        media = content_type.split(";")[0].strip().lower()
        if media not in {"text/plain", "text/markdown", "text/html", "application/xhtml+xml"}:
            return ExtractionData(
                status=ExtractionStatus.UNAVAILABLE,
                version=self.version,
                error_code=ErrorCode.UNSUPPORTED_FILE,
            )
        try:
            encoding = "utf-16" if payload.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
            text = normalize(payload.decode(encoding, errors="strict"))
            if "\x00" in text:
                raise UnicodeError
            if media in {"text/html", "application/xhtml+xml"}:
                parser = HTMLText()
                parser.feed(text)
                text = "".join(parser.parts)
            if len(text) > self.limits.max_extracted_chars:
                return ExtractionData(
                    status=ExtractionStatus.FAILED,
                    version=self.version,
                    error_code=ErrorCode.EXTRACTION_TOO_LARGE,
                )
            if not text.strip():
                return ExtractionData(
                    status=ExtractionStatus.UNAVAILABLE,
                    version=self.version,
                    error_code=ErrorCode.TEXT_UNAVAILABLE,
                )
            return success(text, self.version)
        except (UnicodeError, ValueError):
            return ExtractionData(
                status=ExtractionStatus.FAILED,
                version=self.version,
                error_code=ErrorCode.DECODE_FAILED,
            )

    def _pdf(self, raw: bytes) -> ExtractionData:
        ctx = multiprocessing.get_context("spawn")
        receiving, sending = ctx.Pipe(duplex=False)
        worker = ctx.Process(target=_pdf_worker, args=(raw, self.limits, self.version, sending))
        worker.start()
        sending.close()
        try:
            if not receiving.poll(self.limits.extraction_timeout_seconds):
                return ExtractionData(
                    status=ExtractionStatus.FAILED,
                    version=self.version,
                    error_code=ErrorCode.EXTRACTION_TIMEOUT,
                )
            try:
                data = receiving.recv()
                if not isinstance(data, ExtractionData):
                    raise ValueError
                return data
            except (EOFError, ValueError):
                return ExtractionData(
                    status=ExtractionStatus.FAILED,
                    version=self.version,
                    error_code=ErrorCode.EXTRACTION_FAILED,
                )
        finally:
            receiving.close()
            worker.join(timeout=0.2)
            if worker.is_alive():
                worker.terminate()
                worker.join(timeout=2)
            worker.close()
