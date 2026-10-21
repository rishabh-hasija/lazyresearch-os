# 0006: Temporal boundary for durable Research Missions

## Status

Accepted as the requested design baseline on 2026-10-20 and approved by the user on 2026-10-21. Task 1A implements only the pure domain subset and minimal repository contracts; see STATUS.md. Acceptance is not a claim of implemented integrations or persistence.

## Context

A mission performs many slow external calls, can partially fail, and must resume after restarts without replaying unrelated completed work.

## Decision

Temporal orchestrates whole missions with deterministic workflow code and per-stage/per-source idempotent activities invoking application operations. Store content/results in PostgreSQL and pass IDs through workflow history. Persist dispatch intent with mission creation; reconcile start retries by mission ID.

## Alternatives considered

Wrapping each synchronous function in a workflow adds cost without benefit. An in-memory background task loses durability. Building a homegrown mission engine duplicates the chosen partner's role.

## Consequences

Cancellation, retry budgets, activity idempotency, payload minimization, and replay-compatible deployments are required. Provider calls may be charged twice across crash windows. Ingestion CRUD and ordinary reads stay outside Temporal.

## Future reconsideration triggers

Revisit if measured operational burden outweighs mission recovery value. Engine replacement needs an in-flight-run transition plan. Add schedules only after on-demand missions work.

See [Architecture](../ARCHITECTURE.md) and [Data model](../DATA_MODEL.md) for the shared contracts.

