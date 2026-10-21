from dataclasses import replace

from lazyresearch.application.intake_models import ErrorCode, ExtractionStatus, IntakeLimits
from lazyresearch.domain.content import SourceType
from lazyresearch.infrastructure.sources.extract import SourceTextExtractor


def test_utf8_bom_and_line_endings_preserve_meaning() -> None:
    data = SourceTextExtractor().extract(
        b"\xef\xbb\xbfHello\r\nWorld", SourceType.TEXT, "text/plain"
    )
    assert data.status is ExtractionStatus.SUCCEEDED and data.text == "Hello\nWorld"


def test_utf16_bom_is_supported_without_guessing_legacy_encoding() -> None:
    data = SourceTextExtractor().extract("Hello".encode("utf-16"), SourceType.TEXT, "text/plain")
    assert data.text == "Hello"


def test_html_scripts_are_never_executed_or_indexed() -> None:
    data = SourceTextExtractor().extract(
        b"<html><head><title>title</title></head><p>Hello &amp; welcome</p>"
        b"<script>secret()</script></html>",
        SourceType.URL,
        "text/html; charset=utf-8",
    )
    assert "Hello & welcome" in data.text and "secret" not in data.text


def test_text_output_bound() -> None:
    extractor = SourceTextExtractor(replace(IntakeLimits(), max_extracted_chars=2))
    data = extractor.extract(b"long", SourceType.TEXT, "text/plain")
    assert data.error_code is ErrorCode.EXTRACTION_TOO_LARGE
