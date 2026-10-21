# 0005: Vector store abstraction and pgvector strategy

## Status

Accepted as the requested design baseline on 2026-10-20 and approved by the user on 2026-10-21. Task 1A implements only the pure domain subset and minimal repository contracts; see STATUS.md. Acceptance is not a claim of implemented integrations or persistence.

## Context

Personal research needs semantic matching without sacrificing ownership filters or lexical availability.

## Decision

VectorStore indexes/queries scoped immutable chunk IDs in a named embedding space. Use pgvector initially if available, exact retrieval at demo scale, lexical fallback if absent. Separate embedding generation from storage.

## Alternatives considered

Vector-only retrieval misses exact terms and can hide unembedded content. A standalone vector service adds infrastructure. Hard-coding pgvector calls into application logic makes replacement harder.

## Consequences

Maintain model/dimension identity, deletion propagation, and hybrid evaluation. Approximate indexing is conditional on recall under owner/collection filters. Derived vectors are rebuildable, not canonical evidence.

## Future reconsideration triggers

Revisit after measured corpus size/latency warrants approximate indexes or another store; change embedding model through a parallel index and evaluated cutover.

See [Architecture](../ARCHITECTURE.md) and [Data model](../DATA_MODEL.md) for the shared contracts.

