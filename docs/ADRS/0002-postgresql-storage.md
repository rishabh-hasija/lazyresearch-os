# 0002: PostgreSQL as canonical storage

## Status

Accepted as the requested design baseline on 2026-10-20 and approved by the user on 2026-10-21. Task 1A implements only the pure domain subset and minimal repository contracts; see STATUS.md. Acceptance is not a claim of implemented integrations or persistence.

## Context

Sources, evidence, versions, and actions need referential integrity and transactional publication; exported files cannot be the truth.

## Decision

Use provider-neutral PostgreSQL configured by DATABASE_URL. Store bounded original payloads plus normalized records in DB initially. Keep pgvector optional and exports derived. Use standard driver/SQL semantics, not provider-specific auth/storage SDKs.

## Alternatives considered

SQLite would ease setup but diverge from the deployment/vector target. Files are poor for concurrent relationships. A document store would weaken the chosen transaction/relational model.

## Consequences

Plan migrations, TLS, backup/restore, owner predicates, and explicit runtime/migration credentials. Large binary storage may later need a BlobStore while DB retains canonical metadata.

## Future reconsideration triggers

Reconsider payload storage after measured size/backup pressure; reconsider database only with demonstrated requirements that outweigh migration cost.

See [Architecture](../ARCHITECTURE.md) and [Data model](../DATA_MODEL.md) for the shared contracts.

