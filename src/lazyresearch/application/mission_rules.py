"""Explicit gap, query and conservative conflict heuristics, not an autonomous planner."""

import re
from datetime import datetime, timedelta
from itertools import combinations

from lazyresearch.application.mission_models import (
    Contradiction,
    GapDecision,
    MissionEvidence,
    MissionScope,
)


def public_query(question: str) -> str:
    value = re.sub(r'https?://\S+|[\w.+-]+@[\w.-]+|["“][^"”]*["”]', " ", question)
    value = re.sub(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F-]{27,}\b|\b\w*[_:/@]\w*\b", " ", value)
    value = re.sub(r"\b(?:[A-Z]{2,}-\d+|\w*[a-f0-9]{16,}\w*)\b", " ", value)
    value = re.sub(r"[^\w\s-]", " ", value)
    return " ".join(value.split())[:200]


def detect_gaps(
    question: str, scope: MissionScope, evidence: tuple[MissionEvidence, ...], now: datetime
) -> GapDecision:
    reasons = []
    if len({e.content_id for e in evidence}) < 2:
        reasons.append("insufficient_personal_sources")
    if scope.require_current or re.search(
        r"\b(current|latest|today|pricing|price)\b", question, re.I
    ):
        reasons.append("freshness_gap")
    if evidence and all(
        (e.published_at or e.fetched_at) < now - timedelta(days=scope.freshness_days)
        for e in evidence
    ):
        reasons.append("stale_evidence")
    if (
        re.search(r"\b(compare|versus|comparison)\b", question, re.I)
        and len({e.content_id for e in evidence}) < 2
    ):
        reasons.append("missing_comparison_coverage")
    query = public_query(question)
    permitted = scope.public and scope.max_queries > 0 and scope.max_sources > 0
    # One focused question is the initial strategy; configured maximum remains a hard cap.
    queries = (query,) if permitted and reasons and query else ()
    return GapDecision(reasons=tuple(reasons), permitted=permitted, queries=queries)


def detect_conflicts(evidence: tuple[MissionEvidence, ...]) -> tuple[Contradiction, ...]:
    patterns = {
        "DATE": r"\b\d{4}-\d{2}-\d{2}\b",
        "PRICE": r"(?:(?:[$€£]|EUR|USD|GBP)\s*\d[\d,.]*|\d[\d,.]*\s*(?:EUR|USD|GBP))",
        "QUANTITY": r"\b\d+(?:\.\d+)?\s*(?:kWh|kW|kg|litres)\b",
        "VERSION": r"\bv\d+(?:\.\d+)+\b",
    }
    conflicts = []
    for a, b in combinations(evidence, 2):
        if a.content_id == b.content_id:
            continue
        # Shared topic words are only a heuristic, not semantic equivalence.
        common = set(re.findall(r"\b[a-z]{4,}\b", a.quote.lower())) & set(
            re.findall(r"\b[a-z]{4,}\b", b.quote.lower())
        )
        if not common:
            continue
        recommendations = [bool(re.search(r"\brecommend\b", item.quote, re.I)) for item in (a, b)]
        negative = [
            bool(re.search(r"\b(?:not recommend|avoid|do not buy)\b", item.quote, re.I))
            for item in (a, b)
        ]
        if all(recommendations) and negative[0] != negative[1]:
            conflicts.append(
                Contradiction(
                    evidence_a=a.id,
                    evidence_b=b.id,
                    kind="RECOMMENDATION",
                    description=(
                        "Related sources appear to recommend and discourage an option; "
                        "verify applicability."
                    ),
                )
            )
        for kind, pattern in patterns.items():
            left, right = set(re.findall(pattern, a.quote)), set(re.findall(pattern, b.quote))
            if left and right and left != right:
                conflicts.append(
                    Contradiction(
                        evidence_a=a.id,
                        evidence_b=b.id,
                        kind=kind,  # type: ignore[arg-type]
                        description=(
                            f"Possible {kind.lower()} mismatch in related sources; "
                            "verify scope, units and applicability."
                        ),
                    )
                )
        if a.url and a.url == b.url and a.text_hash != b.text_hash and a.fetched_at != b.fetched_at:
            conflicts.append(
                Contradiction(
                    evidence_a=a.id,
                    evidence_b=b.id,
                    kind="FRESHNESS",
                    description=(
                        "Different snapshots of the same URL; "
                        "newer fetch does not itself establish truth."
                    ),
                )
            )
    return tuple(conflicts[:40])
