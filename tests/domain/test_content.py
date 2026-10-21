from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
from hashlib import sha256
from uuid import UUID

import pytest

from lazyresearch.domain.content import CaptureOccurrence, ContentItem, SourceEvidence, SourceType
from lazyresearch.domain.errors import DomainError
from lazyresearch.domain.identity import CaptureId, ContentId


def test_original_cannot_be_mutated(content: ContentItem) -> None:
    with pytest.raises(FrozenInstanceError):
        content.original_title = "Generated summary"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        content.raw_content = b"replacement"  # type: ignore[misc]
    assert content.raw_content == b"Reply by Friday."


def test_repeat_capture_retains_identity_without_another_snapshot(content: ContentItem) -> None:
    first = CaptureOccurrence(
        id=CaptureId(UUID(int=11)),
        owner_id=content.owner_id,
        content_id=content.id,
        captured_at=content.captured_at,
        intake_reference="batch-1:0",
        submitted_filename="note.txt",
    )
    second = replace(first, id=CaptureId(UUID(int=12)), intake_reference="batch-2:0")
    assert first != second
    assert first.content_id == second.content_id == content.id
    with pytest.raises(FrozenInstanceError):
        first.content_id = ContentId(UUID(int=99))  # type: ignore[misc]


def test_source_update_is_a_separate_snapshot(content: ContentItem) -> None:
    updated_bytes = b"Reply by Monday."
    updated = replace(
        content,
        id=ContentId(UUID(int=10)),
        predecessor_id=content.id,
        raw_content=updated_bytes,
        raw_content_hash=sha256(updated_bytes).hexdigest(),
    )
    assert updated.predecessor_id == content.id
    assert updated.raw_content != content.raw_content
    assert content.predecessor_id is None


def test_hash_must_match_original_bytes(content: ContentItem) -> None:
    with pytest.raises(DomainError, match="does not match"):
        replace(content, raw_content=b"AI rewrote the source")


@pytest.mark.parametrize("digest", ["", "no-hash", "A" * 64, "x" * 64])
def test_hash_format_is_explicit(content: ContentItem, digest: str) -> None:
    with pytest.raises(DomainError, match="SHA-256"):
        replace(content, raw_content_hash=digest)


def test_mutable_raw_buffer_is_rejected(content: ContentItem) -> None:
    with pytest.raises(DomainError, match="immutable bytes"):
        replace(content, raw_content=bytearray(content.raw_content))


def test_self_predecessor_rejected(content: ContentItem) -> None:
    with pytest.raises(DomainError, match="own predecessor"):
        replace(content, predecessor_id=content.id)


@pytest.mark.parametrize("field", ["captured_at", "published_at"])
def test_snapshot_rejects_naive_instants(content: ContentItem, field: str) -> None:
    with pytest.raises(DomainError, match="timezone-aware"):
        replace(content, **{field: datetime(2026, 10, 21)})


def test_aware_instants_normalize_to_utc(content: ContentItem) -> None:
    local = content.captured_at.astimezone(timezone(timedelta(hours=2)))
    normalized = replace(content, captured_at=local, published_at=local)
    assert normalized.captured_at.tzinfo is UTC
    assert normalized.published_at == content.captured_at


def test_capture_rejects_naive_time(content: ContentItem) -> None:
    with pytest.raises(DomainError, match="timezone-aware"):
        CaptureOccurrence(
            id=CaptureId(UUID(int=11)),
            owner_id=content.owner_id,
            content_id=content.id,
            captured_at=datetime(2026, 10, 21),
            intake_reference="batch:0",
        )


def test_url_preserves_both_addresses(content: ContentItem) -> None:
    url = replace(
        content,
        source_type=SourceType.URL,
        original_url="https://example.test/page?edition=1",
        canonical_url="https://example.test/page",
        author="Example Author",
    )
    assert url.original_url != url.canonical_url
    assert url.author == "Example Author"


def test_url_requires_its_original_address(content: ContentItem) -> None:
    with pytest.raises(DomainError, match="original URL"):
        replace(content, source_type=SourceType.URL)


@pytest.mark.parametrize("source_type", list(SourceType))
def test_supported_source_types_have_no_adapter_dependency(
    content: ContentItem,
    source_type: SourceType,
) -> None:
    assert (
        replace(
            content,
            source_type=source_type,
            original_url="https://example.test/source",
        ).source_type
        is source_type
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"start": -1},
        {"end": 0},
        {"end": 15},
        {"quote": ""},
        {"page": 0},
    ],
)
def test_invalid_evidence_locator_is_rejected(
    evidence: SourceEvidence,
    changes: dict[str, object],
) -> None:
    with pytest.raises(DomainError):
        replace(evidence, **changes)


def test_extraction_reference_is_immutable(evidence: SourceEvidence) -> None:
    with pytest.raises(FrozenInstanceError):
        evidence.start = 1  # type: ignore[misc]


def test_invalid_runtime_source_type_is_rejected(content: ContentItem) -> None:
    with pytest.raises(DomainError, match="SourceType"):
        replace(content, source_type="TEXT")
