# 0004: Configurable AI provider abstraction

## Status

Accepted as the requested design baseline on 2026-10-20 and approved by the user on 2026-10-21. Task 1A implements only the pure domain subset and minimal repository contracts; see STATUS.md. Acceptance is not a claim of implemented integrations or persistence.

## Context

Gemma is useful but local resources and model compatibility are unknown. Domain logic must not embed a model family or response format.

## Decision

AIProcessor accepts bounded domain-shaped inputs and returns validated versioned outputs. Bootstrap selects provider/model/endpoint; infrastructure contains runtime SDKs. Record model/prompt/input/schema metadata. Initial candidate Gemma 4 E4B is conditional on benchmarks.

## Alternatives considered

Direct Gemma/runtime calls inside use cases are fast to start but create lock-in. A universal agent framework would widen scope. A chat-only interface would hide required structured output validation.

## Consequences

Adapter contract tests and capability checks are required later. A fallback changes processing version and never overwrites past outputs. Local versus remote data routing must be visible.

## Future reconsideration triggers

Revisit after measured structured-output quality, latency, memory pressure, or provider capability changes; do not silently switch models mid-result.

See [Architecture](../ARCHITECTURE.md) and [Data model](../DATA_MODEL.md) for the shared contracts.

