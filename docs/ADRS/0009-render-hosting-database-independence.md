# 0009: Separate Render hosting from database-provider choice

## Status

Accepted as the requested design baseline on 2026-10-20 and approved by the user on 2026-10-21. Task 1A implements only the pure domain subset and minimal repository contracts; see STATUS.md. Acceptance is not a claim of implemented integrations or persistence.

## Context

Render provides public demo access, but persistence must remain portable and inference/worker resources are unverified.

## Decision

Host public web/API on Render; optionally host the same-release worker there. Configure external PostgreSQL by DATABASE_URL and keep model runtime and Temporal service separately configurable. No requirement to provision Render Postgres.

## Alternatives considered

A single-vendor blueprint is convenient but creates an unnecessary database dependency. Laptop-only hosting misses the public demo goal. Assuming local inference is reachable as localhost from Render is invalid.

## Consequences

Need secure network paths, TLS, credentials, resource budgeting, and independently managed backups. A local outbound Temporal worker can support a supervised demo but is not an always-on hosting promise.

## Future reconsideration triggers

Revisit runtime placement after actual resource/latency/cost tests. Database provider changes use normal migration/restore validation, not domain changes.

See [Architecture](../ARCHITECTURE.md) and [Data model](../DATA_MODEL.md) for the shared contracts.

