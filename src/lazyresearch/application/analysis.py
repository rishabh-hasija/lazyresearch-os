"""Bounded source-only analysis, locator checks and conservative action translation."""

import re
from datetime import date
from uuid import uuid4

from lazyresearch.application.analysis_models import (
    AIError,
    AnalysisConfig,
    AnalysisOutcome,
    AnalysisOutputSchema,
    AnalysisRequest,
    AnalysisSegment,
    AnalysisWork,
    CallAttempt,
    EvidenceLocatorSchema,
)
from lazyresearch.application.intake_models import ContentExtraction
from lazyresearch.domain.actions import ActionOrigin, ActionOriginType, ActionProposal, Deadline
from lazyresearch.domain.analysis import CitedStatement, ContentAnalysis
from lazyresearch.domain.content import SourceEvidence
from lazyresearch.domain.identity import AnalysisId, ExtractionId, OwnerId, ProposalId
from lazyresearch.ports.ai import AIProcessor, AnalysisStore


def segments(extraction: ContentExtraction, config: AnalysisConfig) -> tuple[AnalysisSegment, ...]:
    """Partition the full extraction at page boundaries, then at deterministic char budgets."""
    text = extraction.data.text
    result = []
    boundaries = {0, len(text)}
    for page in extraction.data.pages:
        boundaries.update((page.start, page.end))
    points = sorted(boundaries)
    for left, right in zip(points, points[1:], strict=False):
        page_number = next(
            (p.page for p in extraction.data.pages if p.start <= left and right <= p.end), None
        )
        start = left
        while start < right:
            end, used = start, 0
            while end < right and end - start < config.max_input_chars:
                size = len(text[end].encode("utf-8"))
                if used + size > config.input_byte_budget:
                    break
                used += size
                end += 1
            result.append(AnalysisSegment(start, end, page_number, text[start:end]))
            if len(result) >= config.max_chunks:
                return tuple(result)
            start = end
    return tuple(result)


def resolve(
    locator: EvidenceLocatorSchema, request: AnalysisRequest, extraction: ContentExtraction
) -> SourceEvidence:
    segment = request.segment
    if (
        locator.content_id != request.content_id
        or locator.extraction_id != request.extraction_id
        or not segment.start <= locator.start < locator.end <= segment.end
        or locator.page != segment.page
        or extraction.data.text[locator.start : locator.end] != locator.quote
        or not locator.quote.strip()
    ):
        raise AIError("INVALID_LOCATOR")
    return SourceEvidence(
        owner_id=request.owner_id,
        content_id=extraction.content_id,
        extraction_id=ExtractionId(extraction.id),
        start=locator.start,
        end=locator.end,
        quote=locator.quote,
        page=locator.page,
    )


def normalize_deadline(raw: str | None) -> Deadline:
    """Only a single explicitly written ISO date. Preserve everything else unresolved."""
    if raw:
        dates = re.findall(r"(?<![\w-])\d{4}-\d{2}-\d{2}(?![\w-])", raw)
        if len(dates) == 1 and not re.search(r"\d{1,2}:\d{2}|T\d{2}", raw):
            try:
                return Deadline(raw_text=raw, normalized=date.fromisoformat(dates[0]))
            except ValueError:
                pass
    return Deadline(raw_text=raw)


def assemble(
    work: AnalysisWork, outputs: tuple[tuple[AnalysisRequest, AnalysisOutputSchema], ...]
) -> ContentAnalysis:
    analysis_id = AnalysisId(uuid4())
    claims: list[CitedStatement] = []
    entities: list[CitedStatement] = []
    proposals: list[ActionProposal] = []
    summaries: list[str] = []
    topics: list[str] = []
    for request, output in outputs:
        if output.schema_version != request.config.schema_version:
            raise AIError("INVALID_SCHEMA")
        summaries.append(output.summary)
        topics.extend(t for t in output.topics if t not in topics)
        for statement in output.claims:
            claims.append(
                CitedStatement(
                    text=statement.text,
                    uncertainty=statement.uncertainty,
                    evidence=tuple(
                        resolve(e, request, work.extraction) for e in statement.evidence
                    ),
                )
            )
        for entity in output.entities:
            evidence = tuple(resolve(e, request, work.extraction) for e in entity.evidence)
            if not any(entity.text in e.quote for e in evidence):
                raise AIError("INVALID_LOCATOR")
            entities.append(
                CitedStatement(text=entity.text, uncertainty="medium", evidence=evidence)
            )
        for candidate in output.actions:
            evidence = tuple(resolve(e, request, work.extraction) for e in candidate.evidence)
            if candidate.deadline_raw and not any(
                candidate.deadline_raw in e.quote for e in evidence
            ):
                raise AIError("INVALID_LOCATOR")
            proposals.append(
                ActionProposal(
                    id=ProposalId(uuid4()),
                    owner_id=work.lease.owner_id,
                    title=candidate.title,
                    description=candidate.description,
                    origin=ActionOrigin(
                        kind=ActionOriginType.SOURCE_ANALYSIS, analysis_id=analysis_id
                    ),
                    candidate_ordinal=len(proposals),
                    processing=work.processing,
                    evidence=evidence,
                    deadline=(
                        normalize_deadline(candidate.deadline_raw)
                        if candidate.uncertainty == "low"
                        and len(
                            set(
                                re.findall(
                                    r"\d{4}-\d{2}-\d{2}", " ".join(e.quote for e in evidence)
                                )
                            )
                        )
                        <= 1
                        else Deadline(raw_text=candidate.deadline_raw)
                    ),
                    uncertainty=candidate.uncertainty,
                    kind=candidate.kind,
                )
            )
    states = {o.actionability for _, o in outputs}
    actionability = (
        "action_required"
        if proposals
        else "uncertain"
        if "uncertain" in states
        else "no_action"
        if "no_action" in states
        else "insufficient_information"
    )
    ranges = tuple((r.segment.start, r.segment.end) for r, _ in outputs)
    return ContentAnalysis(
        id=analysis_id,
        owner_id=work.lease.owner_id,
        content_id=work.lease.content_id,
        extraction_id=work.extraction.id,
        run_id=work.run_id,
        version=work.lease.version,
        processing=work.processing,
        summaries=tuple(summaries),
        topics=tuple(topics),
        claims=tuple(claims),
        entities=tuple(entities),
        actionability=actionability,
        proposals=tuple(proposals),
        covered_ranges=ranges,
        total_chars=len(work.extraction.data.text),
        coverage="COMPLETE" if ranges[-1][1] == len(work.extraction.data.text) else "PARTIAL",
    )


class ProcessPendingContent:
    def __init__(
        self, store: AnalysisStore, processor: AIProcessor, config: AnalysisConfig
    ) -> None:
        self.store, self.processor, self.config = store, processor, config

    def process_one(self, owner_id: OwnerId) -> AnalysisOutcome:
        work = self.store.claim(owner_id, self.config)
        if work is None:
            return AnalysisOutcome("IDLE")
        attempts: list[CallAttempt] = []
        try:
            outputs = []
            for segment in segments(work.extraction, self.config):
                self.store.renew(work)
                request = AnalysisRequest(
                    owner_id, work.lease.content_id, work.extraction.id, segment, self.config
                )
                if not segment.text.strip():
                    outputs.append(
                        (
                            request,
                            AnalysisOutputSchema(
                                schema_version=self.config.schema_version,
                                summary="Whitespace separator; no meaningful source information.",
                                topics=(),
                                entities=(),
                                claims=(),
                                actions=(),
                                actionability="insufficient_information",
                            ),
                        )
                    )
                    continue
                result = self.processor.analyze(request)
                attempts.extend(result.attempts)
                outputs.append((request, result.output))
            analysis = assemble(work, tuple(outputs))
        except AIError as exc:
            attempts.extend(exc.attempts)
            self.store.fail(work, exc.code, tuple(attempts))
            return AnalysisOutcome("FAILED", error_code=exc.code)
        # Storage errors deliberately escape: the job remains recoverable, never falsely successful.
        self.store.publish(work, analysis, tuple(attempts))
        return AnalysisOutcome("SUCCEEDED", analysis_id=analysis.id)


def claim_review_cases(analysis: ContentAnalysis) -> tuple[dict[str, object], ...]:
    """Deterministic human-review fixture; no automatic entailment label is inferred."""
    return tuple(
        {
            "analysis_id": str(analysis.id),
            "claim_ordinal": i,
            "claim": c.text,
            "evidence": tuple(e.quote for e in c.evidence),
            "support": "UNREVIEWED",
            "allowed_verdicts": ("SUPPORTED", "UNSUPPORTED", "UNCERTAIN"),
        }
        for i, c in enumerate(analysis.claims)
    )
