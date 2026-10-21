"""Stage operations used by Temporal; large payloads remain in canonical storage."""

import json
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from lazyresearch.application.intake import IntakeService
from lazyresearch.application.intake_models import IntakeInput
from lazyresearch.application.mission_models import (
    Contradiction,
    MissionError,
    MissionEvidence,
    ResearchBrief,
    SearchHit,
    SynthesisRequest,
    TransientMissionError,
    validate_brief,
)
from lazyresearch.application.mission_rules import detect_conflicts, detect_gaps
from lazyresearch.application.retrieval import RetrieveEvidence
from lazyresearch.application.retrieval_models import RetrievalRequest
from lazyresearch.domain.content import SourceType
from lazyresearch.domain.identity import OwnerId
from lazyresearch.ports.mission import MissionStore, ResearchSynthesizer, SearchProvider


def evidence_values(payload: dict[str, object]) -> tuple[MissionEvidence, ...]:
    return tuple(
        MissionEvidence.model_validate_json(json.dumps(e))
        for e in cast(list[object], payload.get("evidence", []))
    )


class ResearchOperations:
    def __init__(
        self,
        store: MissionStore,
        retrieval: RetrieveEvidence,
        intake: IntakeService,
        search: SearchProvider,
        synthesizer: ResearchSynthesizer,
    ) -> None:
        self.store, self.retrieval, self.intake = store, retrieval, intake
        self.search, self.synthesizer = search, synthesizer

    def personal_search(self, owner: UUID, mission: UUID) -> None:
        if self.store.stage(owner, mission, "personal_search") is not None:
            return
        self.store.check(owner, mission)
        scope = self.store.scope(owner, mission)
        evidence: tuple[MissionEvidence, ...] = ()
        limitations = []
        if scope.personal:
            self.retrieval.store.index(OwnerId(owner), self.retrieval.chunks)
            result = self.retrieval.retrieve(
                RetrievalRequest(
                    owner_id=OwnerId(owner),
                    query=str(self.store.context(owner, mission)["question"]),
                    collection_ids=scope.collection_ids,
                    lexical=scope.lexical,
                    vector=scope.vector,
                    limit=min(scope.max_evidence, self.retrieval.default_limit),
                    per_source=self.retrieval.default_per_source,
                )
            )
            evidence = self.store.candidates(
                owner,
                mission,
                tuple(c.chunk.id for c in result.candidates),
                "PERSONAL",
                "hybrid"
                if scope.vector and scope.lexical
                else "vector"
                if scope.vector
                else "lexical",
            )
            if scope.vector and result.vector_status != "USED":
                limitations.append("semantic_retrieval_unavailable_lexical_fallback")
        self.store.save_stage(
            owner,
            mission,
            "personal_search",
            {"evidence": [e.model_dump(mode="json") for e in evidence], "limitations": limitations},
        )

    def gap_detection(self, owner: UUID, mission: UUID) -> int:
        saved = self.store.stage(owner, mission, "gap_detection")
        if saved is None:
            self.store.check(owner, mission)
            evidence = evidence_values(self.store.stage(owner, mission, "personal_search") or {})
            decision = detect_gaps(
                str(self.store.context(owner, mission)["question"]),
                self.store.scope(owner, mission),
                evidence,
                datetime.now(UTC),
            )
            payload = decision.model_dump(mode="json")
            payload["limitations"] = (
                list(decision.reasons) if decision.reasons and not decision.queries else []
            )
            saved = self.store.save_stage(owner, mission, "gap_detection", payload)
        return len(cast(list[str], saved["queries"]))

    def public_search(
        self, owner: UUID, mission: UUID, query_index: int, *, final_attempt: bool = False
    ) -> None:
        name = f"public_search:{query_index}"
        if self.store.stage(owner, mission, name) is not None:
            return
        self.store.check(owner, mission)
        scope = self.store.scope(owner, mission)
        gap = self.store.stage(owner, mission, "gap_detection") or {}
        queries = cast(list[str], gap.get("queries", []))
        if not scope.public or not 0 <= query_index < min(len(queries), scope.max_queries):
            raise MissionError("SEARCH_NOT_PERMITTED")
        try:
            hits = self.search.search(queries[query_index], scope.max_sources)
            payload: dict[str, object] = {
                "hits": [h.model_dump(mode="json") for h in hits[: scope.max_sources]],
                "query": queries[query_index],
            }
        except MissionError as exc:
            if isinstance(exc, TransientMissionError) and not final_attempt:
                raise
            payload = {
                "hits": [],
                "limitations": ["public_search_unavailable"],
                "query": queries[query_index],
            }
        self.store.save_stage(owner, mission, name, payload)

    def select_sources(self, owner: UUID, mission: UUID) -> int:
        saved = self.store.stage(owner, mission, "select_sources")
        if saved is None:
            self.store.check(owner, mission)
            scope = self.store.scope(owner, mission)
            hits: list[dict[str, object]] = []
            seen: set[str] = set()
            for i in range(scope.max_queries):
                result = self.store.stage(owner, mission, f"public_search:{i}") or {}
                for raw in cast(list[dict[str, object]], result.get("hits", [])):
                    hit = SearchHit.model_validate_json(json.dumps(raw))
                    key = hit.url.split("#")[0]
                    if key not in seen and len(hits) < scope.max_sources:
                        seen.add(key)
                        hits.append({**hit.model_dump(mode="json"), "query_index": i})
            saved = self.store.save_stage(owner, mission, "select_sources", {"hits": hits})
        return len(cast(list[object], saved["hits"]))

    def fetch_source(
        self,
        owner: UUID,
        mission: UUID,
        source_index: int,
        *,
        final_attempt: bool = False,
        retry_attempt: bool = False,
    ) -> None:
        name = f"fetch_sources:{source_index}"
        if self.store.stage(owner, mission, name) is not None:
            return
        self.store.check(owner, mission)
        if not self.store.scope(owner, mission).public:
            raise MissionError("SEARCH_NOT_PERMITTED")
        selection = self.store.stage(owner, mission, "select_sources") or {}
        hits = cast(list[dict[str, object]], selection.get("hits", []))
        if not 0 <= source_index < len(hits):
            raise MissionError("INVALID_SOURCE_INDEX")
        hit = hits[source_index]
        result = self.intake.ingest(
            OwnerId(owner),
            f"mission:{mission}:source:{source_index}",
            (
                IntakeInput(
                    source_type=SourceType.URL, url=str(hit["url"]), title=str(hit["title"])
                ),
            ),
        )
        if result.entries[0].content_id is None and retry_attempt:
            result = self.intake.resume(OwnerId(owner), result.batch_id, retry_failed=True)
        entry = result.entries[0]
        if entry.content_id is None:
            transient = str(entry.error_code) in {"FETCH_TIMEOUT", "FETCH_FAILED"} or (
                str(entry.error_code) == "HTTP_ERROR"
                and (
                    entry.http_status == 429
                    or (entry.http_status is not None and entry.http_status >= 500)
                )
            )
            if not final_attempt and transient:
                raise TransientMissionError("FETCH_TRANSIENT")
            payload: dict[str, object] = {
                "content_id": None,
                "limitations": ["inaccessible_public_source"],
                "discovery": hit,
            }
        else:
            payload = {"content_id": str(entry.content_id), "discovery": hit}
        self.store.save_stage(owner, mission, name, payload)

    def process_source(self, owner: UUID, mission: UUID, source_index: int) -> None:
        name = f"process_sources:{source_index}"
        if self.store.stage(owner, mission, name) is not None:
            return
        self.store.check(owner, mission)
        fetched = self.store.stage(owner, mission, f"fetch_sources:{source_index}") or {}
        evidence: tuple[MissionEvidence, ...] = ()
        if fetched.get("content_id"):
            content = UUID(str(fetched["content_id"]))
            self.intake.extract_saved(OwnerId(owner), content)  # type: ignore[arg-type]
            self.retrieval.store.index(OwnerId(owner), self.retrieval.chunks)
            ids = self.store.source_chunks(owner, content, self.retrieval.chunks.identity)
            evidence = self.store.candidates(owner, mission, ids[:2], "PUBLIC", "public_fetched")
        self.store.save_stage(
            owner,
            mission,
            name,
            {
                "evidence": [e.model_dump(mode="json") for e in evidence],
                "limitations": [] if evidence else ["public_source_without_usable_text"],
            },
        )

    def freeze_evidence(self, owner: UUID, mission: UUID) -> None:
        scope = self.store.scope(owner, mission)
        values = list(evidence_values(self.store.stage(owner, mission, "personal_search") or {}))
        for i in range(scope.max_sources):
            values.extend(
                evidence_values(self.store.stage(owner, mission, f"process_sources:{i}") or {})
            )
        selected: list[MissionEvidence] = []
        seen = set()
        chars = 0
        # Round-robin origins prevents personal evidence exhausting the entire budget.
        values.sort(key=lambda e: (e.rank, e.origin, str(e.chunk_id)))
        for e in values:
            if e.chunk_id in seen:
                continue
            if (
                len(selected) >= scope.max_evidence
                or chars + len(e.quote) > scope.max_evidence_chars
            ):
                continue
            seen.add(e.chunk_id)
            chars += len(e.quote)
            selected.append(e)
        self.store.freeze(owner, mission, tuple(selected))
        self.store.save_stage(
            owner,
            mission,
            "freeze_evidence",
            {
                "count": len(selected),
                "limitations": ["evidence_budget_truncated"]
                if len(selected) < len({e.chunk_id for e in values})
                else [],
            },
        )

    def detect_contradictions(self, owner: UUID, mission: UUID) -> None:
        if self.store.stage(owner, mission, "detect_conflicts") is not None:
            return
        conflicts = detect_conflicts(self.store.evidence(owner, mission))
        self.store.save_stage(
            owner,
            mission,
            "detect_conflicts",
            {"conflicts": [c.model_dump(mode="json") for c in conflicts]},
        )

    def synthesize(self, owner: UUID, mission: UUID) -> None:
        if self.store.stage(owner, mission, "synthesize") is not None:
            return
        self.store.check(owner, mission)
        self.store.validate_evidence(owner, mission)
        baseline = self.store.baseline(owner, mission)
        baseline_brief = (
            ResearchBrief.model_validate_json(json.dumps(baseline["brief"])) if baseline else None
        )
        conflicts = self.store.stage(owner, mission, "detect_conflicts") or {}
        request = SynthesisRequest(
            question=str(self.store.context(owner, mission)["question"]),
            scope=self.store.scope(owner, mission),
            evidence=self.store.evidence(owner, mission),
            contradictions=tuple(
                Contradiction.model_validate_json(json.dumps(c))
                for c in cast(list[object], conflicts.get("conflicts", []))
            ),
            baseline_summary=baseline_brief.summary.text if baseline_brief else None,
        )
        output = self.synthesizer.synthesize(request)
        validate_brief(output.brief, request.evidence)
        self.store.save_stage(owner, mission, "synthesize", output.model_dump(mode="json"))

    def validate(self, owner: UUID, mission: UUID) -> None:
        self.store.check(owner, mission)
        self.store.validate_evidence(owner, mission)
        self.store.save_stage(owner, mission, "extract_actions", {"validated": True})
