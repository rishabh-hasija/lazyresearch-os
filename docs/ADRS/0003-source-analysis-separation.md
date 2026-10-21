# 0003: Separate source snapshots from generated analysis

## Status

Accepted as the requested design baseline on 2026-10-20 and approved by the user on 2026-10-21. Task 1A implements only the pure domain subset and minimal repository contracts; see STATUS.md. Acceptance is not a claim of implemented integrations or persistence.

## Context

A new prompt/model/parser must not rewrite evidence supporting old answers; identical content can have multiple capture origins.

## Decision

ContentItem retains immutable original bytes and source metadata. CaptureOccurrence records intake history; ContentExtraction versions parsed text; ContentAnalysis versions generated output. Chunks and citations bind to extraction versions. Keep raw and normalized hashes distinct.

## Alternatives considered

Overwriting summary/raw_text fields is easy but destroys provenance. A full event-sourcing framework is unnecessary; append-only successful artifacts plus mutable operational state suffice.

## Consequences

Storage grows; retention/deletion must purge derived sensitive text as well as originals. Raw duplicates may share a snapshot only under documented owner/source identity rules. Similarity never authorizes merging.

## Future reconsideration triggers

Revisit decomposition only when real query/performance needs justify it; privacy deletion always overrides ordinary history availability.

See [Architecture](../ARCHITECTURE.md) and [Data model](../DATA_MODEL.md) for the shared contracts.

