"""Pure display/input mapping; no persistence or ranking/lifecycle policies."""

import re
from pathlib import PurePath
from urllib.parse import urlsplit

from lazyresearch.application.intake_models import EntryReceipt, IntakeInput
from lazyresearch.domain.actions import ActionItem
from lazyresearch.domain.content import SourceType

GROUPS = {
    "READ": "Read now",
    "KEEP": "Useful later",
    "ACT": "Action required",
    "IGNORE": "Low priority",
}


def receipt_status(entry: EntryReceipt) -> str:
    disposition = entry.disposition.value.capitalize()
    if entry.disposition.value == "FAILED":
        return "Failed"
    extraction = entry.extraction_status.value
    if extraction in {"FAILED", "UNAVAILABLE"}:
        return disposition + " · extraction " + extraction.lower()
    return disposition + (
        " · analysis pending or available below"
        if extraction == "SUCCEEDED"
        else " · extraction pending"
    )


STAGES = {
    "mission_created": "Queued",
    "personal_search": "Searching saved sources",
    "gap_detection": "Checking information gaps",
    "public_search": "Checking current public information",
    "select_sources": "Choosing sources",
    "fetch_sources": "Saving public sources",
    "process_sources": "Processing sources",
    "freeze_evidence": "Preparing evidence",
    "detect_conflicts": "Checking contradictions",
    "synthesize": "Writing your brief",
    "extract_actions": "Validating citations and actions",
    "publish": "Publishing your brief",
    "complete": "Complete",
}


def inputs(
    urls: str, uploads: tuple[tuple[str, bytes], ...], text: str, title: str
) -> tuple[IntakeInput, ...]:
    entries = [
        IntakeInput(source_type=SourceType.URL, url=line.strip())
        for line in urls.splitlines()
        if line.strip()
    ]
    for name, data in uploads:
        kind = {
            ".pdf": SourceType.PDF,
            ".md": SourceType.MARKDOWN,
            ".markdown": SourceType.MARKDOWN,
        }.get(PurePath(name).suffix.lower(), SourceType.TEXT)
        entries.append(IntakeInput(source_type=kind, payload=data, filename=name))
    if text.strip():
        entries.append(
            IntakeInput(
                source_type=SourceType.TEXT, payload=text.encode(), title=title.strip() or None
            )
        )
    return tuple(entries)


def mission_status(status: str, stage: str) -> str:
    if status in {"QUEUED", "COMPLETED", "PARTIAL", "FAILED", "CANCELLED"}:
        return {"COMPLETED": "Complete", "PARTIAL": "Partial coverage"}.get(
            status, status.capitalize()
        )
    return STAGES.get(stage, "Research in progress")


def ranking_mode(mode: str) -> str:
    return (
        "Personalized for you · evaluated TabPFN ranking active."
        if mode == "PERSONAL"
        else "Learning your preferences · using baseline ranking until explicit feedback "
        "and evaluation support personalization."
    )


def ranking_reason(reason: str) -> str:
    return {
        "MODEL_DISABLED": "Rules baseline",
        "MODEL_UNAVAILABLE": "Model unavailable; using rules",
        "MODEL_UNAVAILABLE_OR_INVALID": "Model prediction unavailable; using rules",
        "COLD_START": "More explicit feedback needed",
        "NO_HELDOUT_IMPROVEMENT": "Rules performed at least as well in evaluation",
        "EVALUATED_CONTEXT": "Based on evaluated feedback",
        "USER_OVERRIDE": "Your explicit choice",
        "POTENTIAL_DEADLINE": "Potential deadline",
        "SOURCE_ACTION": "Source-backed action",
        "REPETITIVE": "Repeated capture",
        "ANALYSIS_PENDING": "Analysis pending",
        "RECENT": "Saved recently",
        "OLDER_REFERENCE": "Older reference material",
        "INTEREST_MATCH": "Matches an interest",
        "LOW_RELEVANCE_SUGGESTION": "Low priority suggestion",
    }.get(reason, "Ranking suggestion")


def deadline(item: ActionItem) -> str:
    if item.deadline.normalized is not None:
        return item.deadline.normalized.isoformat()
    if item.deadline.raw_text:
        return item.deadline.raw_text + " · date/time needs review"
    return "No deadline detected"


def safe_url(value: str | None) -> str | None:
    try:
        parsed = urlsplit(value or "")
        return (
            value
            if parsed.scheme in {"https", "http"} and parsed.hostname and not parsed.username
            else None
        )
    except ValueError:
        return None


def claim_text(text: str, evidence_ids: tuple[str, ...]) -> str:
    # Replace display-only UUID labels, retaining the exact stored evidence registry.
    for i, identity in enumerate(evidence_ids, 1):
        text = text.replace(identity, f"Evidence {i}")
    return text


def plain(text: str) -> str:
    # Source/model text cannot introduce remote images, HTML, links or hidden formatting.
    return re.sub(r"([\\`*_{}\[\]()<>#+|~-])", r"\\\1", text)


def error_message(error: Exception) -> str:
    from lazyresearch.application.analysis_models import AIError
    from lazyresearch.ports.errors import RepositoryConflict, RepositoryError

    if isinstance(error, RepositoryConflict):
        return "This item changed or is unavailable. Refresh and try again."
    if isinstance(error, RepositoryError):
        return (
            "The database is unavailable or needs migration. Your previously "
            "saved items remain stored. Check setup, then refresh."
        )
    if isinstance(error, AIError):
        return (
            "The configured processing model is unavailable. "
            "Check Ollama and the model settings. Originals are retained."
        )
    if isinstance(error, ValueError) and str(error) == "DATABASE_URL is required":
        return "No database is configured. Set DATABASE_URL and run migrations before refreshing."
    if isinstance(error, ValueError):
        return "Check the submitted fields and configured limits, then try again."
    return (
        "The operation could not finish. Check the configured services and "
        "try again. Saved originals are retained."
    )


def action_description(title: str, description: str) -> str:
    """Hide only a repeated display title; keep the stored task/proposal untouched."""

    def normalized(value: str) -> str:
        return " ".join(value.split()).casefold().rstrip(".")

    return "" if normalized(title) == normalized(description) else description
