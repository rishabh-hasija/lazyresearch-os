# 0008: Immutable research results and historical evidence

## Status

Accepted as the requested design baseline on 2026-10-20 and approved by the user on 2026-10-21. Task 1A implements only the pure domain subset and minimal repository contracts; see STATUS.md. Acceptance is not a claim of implemented integrations or persistence.

## Context

Repeat research must show what changed, remain auditable, and tolerate failures and concurrent runs.

## Decision

ResearchTopic groups missions. Each mission freezes question/scope/baseline and yields at most one immutable result. Allocate result version under topic lock at publication; unique mission result prevents retry duplication. Current Brief points to the successful result with highest mission run_sequence, not necessarily highest publication version.

## Alternatives considered

Overwriting one topic answer loses history. Export-file versioning is not transactional or canonical. A mutable result draft should not be confused with a published brief.

## Consequences

Concurrent completion order is explicit. A failed rerun leaves Current Brief. Diffs name the frozen baseline, distinguish model-only changes, and preserve evidence snapshot IDs. Privacy deletion can redact/unavailable historical content with tombstones.

## Future reconsideration triggers

Revisit UI ordering after user testing; collaborative branching/merging is out of MVP. Never reinterpret old source snapshots as current evidence.

See [Architecture](../ARCHITECTURE.md) and [Data model](../DATA_MODEL.md) for the shared contracts.

