import pytest

from lazyresearch.domain.content import SourceType
from lazyresearch.ports.errors import RepositoryConflict, RepositoryError
from lazyresearch.ui.presenters import (
    action_description,
    claim_text,
    error_message,
    inputs,
    mission_status,
    plain,
    ranking_mode,
    safe_url,
)


def test_mixed_inputs_preserve_bytes_order_and_invalid_siblings():
    result = inputs(
        "https://example.com\n\n file:///bad \n",
        (("a.md", b"# Original"), ("a.pdf", b"%PDF-original"), ("a.TXT", b"Original")),
        "  pasted  ",
        " Title ",
    )
    assert len(result) == 6
    assert result[1].url == "file:///bad"
    assert result[2].source_type == SourceType.MARKDOWN and result[2].payload == b"# Original"
    assert result[3].source_type == SourceType.PDF
    assert result[4].source_type == SourceType.TEXT
    assert result[-1].payload == b"  pasted  " and result[-1].title == "Title"


@pytest.mark.parametrize(
    "status,stage,expected",
    [
        ("QUEUED", "mission_created", "Queued"),
        ("RUNNING", "personal_search", "Searching saved sources"),
        ("RUNNING", "public_search", "Checking current public information"),
        ("PARTIAL", "complete", "Partial coverage"),
        ("CANCELLED", "synthesize", "Cancelled"),
        ("RUNNING", "future", "Research in progress"),
    ],
)
def test_actual_stage_labels(status, stage, expected):
    assert mission_status(status, stage) == expected


def test_mode_urls_untrusted_text_and_sanitized_errors():
    assert "baseline" in ranking_mode("BASELINE")
    assert "Personalized for you" in ranking_mode("PERSONAL")
    assert "Learning your preferences" in ranking_mode("BASELINE")
    assert safe_url("javascript:alert(1)") is None
    assert safe_url("https://user:secret@example.com") is None
    assert safe_url("https://example.com/doc") == "https://example.com/doc"
    assert "\\[" in plain("![untrusted](https://tracker.example/x)")
    assert claim_text("Fact [abc]", ("abc",)) == "Fact [Evidence 1]"
    for exc in (RepositoryError("SECRET"), RepositoryConflict("SECRET"), RuntimeError("SECRET")):
        assert "SECRET" not in error_message(exc)


@pytest.mark.parametrize(
    "title,description,expected",
    [
        ("Review warranty", "Review warranty", ""),
        ("Review warranty", "Review warranty.", ""),
        ("Review warranty", "  REVIEW   warranty  ", ""),
        ("Review warranty", "Review warranty by Friday", "Review warranty by Friday"),
        ("Review warranty", "", ""),
    ],
)
def test_action_description_hides_only_repeated_title(title, description, expected):
    assert action_description(title, description) == expected
