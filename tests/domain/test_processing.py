from dataclasses import FrozenInstanceError, replace

import pytest

from lazyresearch.domain.actions import ActionProposal
from lazyresearch.domain.content import ContentItem
from lazyresearch.domain.errors import DomainError
from lazyresearch.domain.processing import ProcessingIdentity
from lazyresearch.domain.research import ResearchResult


def test_unknown_revisions_are_not_fabricated(processing: ProcessingIdentity) -> None:
    assert processing.model_revision is None
    assert processing.provider_revision is None
    known = replace(processing, model_revision="weights-1", provider_revision="runtime-2")
    assert known.model_revision == "weights-1"
    assert processing.model_revision is None


def test_generated_outputs_retain_processing_identity(
    result: ResearchResult,
    proposal: ActionProposal,
    processing: ProcessingIdentity,
) -> None:
    assert result.processing == proposal.processing == processing


def test_reprocessing_does_not_change_source_or_previous_identity(
    content: ContentItem,
    processing: ProcessingIdentity,
) -> None:
    before = content.raw_content, content.raw_content_hash
    newer = replace(processing, model="different-model", prompt_version="2")
    assert newer != processing
    assert newer.input_hash == processing.input_hash == content.raw_content_hash
    assert (content.raw_content, content.raw_content_hash) == before
    assert not hasattr(content, "processing")


def test_processing_identity_is_immutable(processing: ProcessingIdentity) -> None:
    with pytest.raises(FrozenInstanceError):
        processing.model = "replacement"  # type: ignore[misc]


@pytest.mark.parametrize(
    "field",
    [
        "provider",
        "model",
        "prompt_version",
        "schema_version",
        "pipeline_version",
        "model_revision",
        "provider_revision",
    ],
)
def test_processing_rejects_blank_version_information(
    processing: ProcessingIdentity,
    field: str,
) -> None:
    with pytest.raises(DomainError, match="nonblank"):
        replace(processing, **{field: " "})


@pytest.mark.parametrize("field", ["input_hash", "prompt_hash"])
def test_processing_requires_explicit_hash_format(
    processing: ProcessingIdentity,
    field: str,
) -> None:
    with pytest.raises(DomainError, match="SHA-256"):
        replace(processing, **{field: "not-a-digest"})
