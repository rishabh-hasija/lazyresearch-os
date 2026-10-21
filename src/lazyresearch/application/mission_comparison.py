"""Conservative deterministic comparison; absence is not falsity."""

import json
from typing import cast

from lazyresearch.application.mission_models import MissionEvidence, ResearchBrief


def compare_results(
    baseline: dict[str, object] | None,
    brief: ResearchBrief,
    evidence: tuple[MissionEvidence, ...],
    processing: dict[str, object],
) -> dict[str, object]:
    if baseline is None:
        return {"baseline": None, "new_sources": sorted({str(e.content_id) for e in evidence})}
    old = ResearchBrief.model_validate_json(json.dumps(baseline["brief"]))
    previous = tuple(
        MissionEvidence.model_validate_json(json.dumps(e))
        for e in cast(list[dict[str, object]], baseline["evidence"])
    )

    def snapshots(items: tuple[MissionEvidence, ...]) -> dict[str, set[str]]:
        result: dict[str, set[str]] = {}
        for item in items:
            result.setdefault(item.url or str(item.content_id), set()).add(str(item.content_id))
        return result

    before, after = snapshots(previous), snapshots(evidence)
    old_claims = {c.text for c in old.cited() if hasattr(c, "text")}
    new_claims = {c.text for c in brief.cited() if hasattr(c, "text")}
    changed = sorted(k for k in before.keys() & after.keys() if before[k] != after[k])
    evidence_changed = {(e.chunk_id, e.text_hash) for e in previous} != {
        (e.chunk_id, e.text_hash) for e in evidence
    }
    recommendations = [c.text for c in old.recommendations] != [
        c.text for c in brief.recommendations
    ]
    actions = [a.model_dump(exclude={"evidence"}) for a in old.action_candidates] != [
        a.model_dump(exclude={"evidence"}) for a in brief.action_candidates
    ]
    categories = []
    if before != after:
        categories.append("SOURCE_CHANGE")
    if evidence_changed:
        categories.append("EVIDENCE_CHANGE")
    if recommendations:
        categories.append("RECOMMENDATION_CHANGE")
    if actions:
        categories.append("ACTION_CHANGE")
    if not evidence_changed and (
        baseline.get("processing") != processing or old_claims != new_claims or actions
    ):
        categories.append("MODEL_ONLY_CHANGE")
    return {
        "categories": categories,
        "new_sources": sorted(after.keys() - before.keys()),
        "removed_sources": sorted(before.keys() - after.keys()),
        "changed_snapshots": changed,
        "new_claims": sorted(new_claims - old_claims),
        "removed_claims": sorted(old_claims - new_claims),
        "unchanged_conclusions": sorted(old_claims & new_claims),
        "recommendations_changed": recommendations,
        "actions_changed": actions,
        "new_actions": sorted(
            {a.title for a in brief.action_candidates} - {a.title for a in old.action_candidates}
        ),
        "changed_actions": [
            a.title
            for a in brief.action_candidates
            for b in old.action_candidates
            if a.title == b.title
            and a.model_dump(exclude={"evidence"}) != b.model_dump(exclude={"evidence"})
        ],
        "changed_claims": [
            {"before": a.text, "after": b.text, "matching": "position_heuristic"}
            for a, b in zip(old.findings, brief.findings, strict=False)
            if a.text != b.text
        ],
        "note": "Removed evidence is unavailable in this run, not proof a claim became false.",
    }
