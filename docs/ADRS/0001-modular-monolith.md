# 0001: Modular monolith vs microservices

## Status

Accepted as the requested design baseline on 2026-10-20 and approved by the user on 2026-10-21. Task 1A implements only the pure domain subset and minimal repository contracts; see STATUS.md. Acceptance is not a claim of implemented integrations or persistence.

## Context

A five-day solo project needs clear replaceable partner boundaries without distributed product services.

## Decision

Use one codebase and release, with pure domain, application, ports, infrastructure, API, UI, and composition root. Web and worker execution roles share the release and database; they are not microservices.

## Alternatives considered

An unstructured monolith is simpler initially but makes provider replacement hard. Microservices add network contracts, deployment overhead, and distributed consistency without a demonstrated need.

## Consequences

Enforce imports and module ownership with later tests. Shared database does not permit arbitrary cross-module ORM access. Avoid generic messaging frameworks.

## Future reconsideration triggers

Revisit only when measured independent scaling/team ownership requires a service boundary; not merely because a partner uses a remote API.

See [Architecture](../ARCHITECTURE.md) and [Data model](../DATA_MODEL.md) for the shared contracts.

